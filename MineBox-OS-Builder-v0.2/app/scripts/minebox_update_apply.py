#!/usr/bin/python3
"""Apply a MineBox GitHub update into the live install directory.

Production (root via systemd):
  clones GitHub, stages app files, swaps /opt/minebox, restarts minebox-api.

Development (--dev):
  stages into a temporary next directory and rsyncs into MINEBOX_UPDATE_TARGET
  (the local app/ tree) without systemd.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO = "https://github.com/heiligg/MineBox.git"
DEFAULT_BRANCH = "main"
DEFAULT_APP_SUBDIR = "MineBox-OS-Builder-v0.2/app"
CONFIG_FILE = Path("/etc/minebox/updates.conf")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict[str, str]:
    values: dict[str, str] = {}
    if CONFIG_FILE.is_file():
        try:
            for raw in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
        except OSError:
            pass
    return values


def cfg(name: str, default: str = "") -> str:
    env_map = {
        "repo": "MINEBOX_UPDATE_REPO",
        "branch": "MINEBOX_UPDATE_BRANCH",
        "app_subdir": "MINEBOX_UPDATE_APP_SUBDIR",
    }
    env_name = env_map.get(name, f"MINEBOX_UPDATE_{name.upper()}")
    if os.environ.get(env_name, "").strip():
        return os.environ[env_name].strip()
    file_values = load_config()
    if name in file_values and file_values[name]:
        return file_values[name]
    return default


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def log(path: Path, message: str) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now()}] {message.rstrip()}\n")


def status(path: Path, state: str, message: str, **extra: Any) -> None:
    write_json(
        path,
        {
            "state": state,
            "message": message,
            "updated_at": now(),
            **extra,
        },
    )


def run(
    command: list[str],
    *,
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=process_env,
    )
    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"Command failed: {' '.join(command)}"
        )
        raise RuntimeError(detail)
    return result


def soft_systemctl(args: list[str], *, timeout: int = 20) -> None:
    """Best-effort systemctl that must never fail an OTA on hang/timeout."""
    try:
        subprocess.run(
            ["systemctl", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return


def restart_dnsmasq_safe() -> None:
    """Bounce hotspot DHCP/DNS without blocking OTA on systemd hangs."""
    soft_systemctl(["daemon-reload"], timeout=30)
    soft_systemctl(["kill", "-s", "SIGKILL", "dnsmasq.service"], timeout=10)
    subprocess.run(
        ["killall", "-9", "dnsmasq"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    soft_systemctl(["reset-failed", "dnsmasq.service"], timeout=10)
    # --no-block avoids the 60s+ hangs we saw from resolvconf/forking helpers.
    soft_systemctl(["start", "--no-block", "dnsmasq.service"], timeout=15)
    time.sleep(1.5)


def safe_remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def resolve_app_dir(clone_root: Path, configured: str) -> Path:
    candidates = [
        clone_root / configured,
        clone_root / "MineBox-OS-Builder-v0.2" / "app",
        clone_root / "app",
    ]
    for candidate in candidates:
        if (candidate / "api" / "server.py").is_file():
            return candidate
    raise RuntimeError(
        "Downloaded release does not contain a MineBox app directory."
    )


def validate_app(app_dir: Path) -> None:
    required = [
        app_dir / "api" / "server.py",
        app_dir / "services" / "updates.py",
        app_dir / "scripts" / "minebox_update_apply.py",
    ]
    missing = [
        str(path.relative_to(app_dir))
        for path in required
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(
            "Downloaded release is incompatible; missing: "
            + ", ".join(missing)
        )


def copy_app_tree(app_dir: Path, destination: Path, builder_root: Path) -> None:
    safe_remove(destination)
    shutil.copytree(
        app_dir,
        destination,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.backup",
            "*.backup-*",
            "*.bak",
            ".venv",
            "runtime",
        ),
    )
    requirements = builder_root / "requirements.txt"
    if not requirements.is_file():
        requirements = app_dir.parent / "requirements.txt"
    if requirements.is_file():
        shutil.copy2(requirements, destination / "requirements.txt")


def _tls_enabled() -> bool:
    return Path("/var/lib/minebox/tls/enabled").is_file()


def _health_urls(preferred: str) -> list[str]:
    """Return HTTP/HTTPS health URLs to try (dashboard may be TLS-only)."""
    preferred = (preferred or "").strip() or "http://127.0.0.1:8080/api/v1/health"
    urls: list[str] = []

    def add(url: str) -> None:
        if url and url not in urls:
            urls.append(url)

    if preferred.startswith("https://"):
        add(preferred)
        add("http://" + preferred[len("https://") :])
    elif preferred.startswith("http://"):
        if _tls_enabled():
            add("https://" + preferred[len("http://") :])
            add(preferred)
        else:
            add(preferred)
            add("https://" + preferred[len("http://") :])
    else:
        add(preferred)

    # Always include the local defaults last as a safety net.
    if _tls_enabled():
        add("https://127.0.0.1:8080/api/v1/health")
        add("http://127.0.0.1:8080/api/v1/health")
    else:
        add("http://127.0.0.1:8080/api/v1/health")
        add("https://127.0.0.1:8080/api/v1/health")
    return urls


def _probe_health(url: str, timeout: float = 3.0) -> bool:
    context = None
    if url.startswith("https://"):
        import ssl

        context = ssl._create_unverified_context()
    with urllib.request.urlopen(url, timeout=timeout, context=context) as response:
        return 200 <= int(response.status) < 500


def healthy(url: str, timeout: int = 60) -> bool:
    """Wait until the dashboard answers on HTTP and/or HTTPS."""
    candidates = _health_urls(url)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for candidate in candidates:
            try:
                if _probe_health(candidate):
                    return True
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                continue
        time.sleep(1)
    return False


def git_env() -> dict[str, str]:
    env: dict[str, str] = {}
    deploy_key = Path(
        os.environ.get(
            "MINEBOX_UPDATE_DEPLOY_KEY",
            "/home/minebox/.ssh/minebox_update",
        )
    )
    if deploy_key.is_file():
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {deploy_key} "
            "-o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=accept-new "
            "-o BatchMode=yes"
        )
    return env


def effective_repo_url(repo: str) -> str:
    """Rewrite GitHub HTTPS → SSH when the MineBox deploy key is present."""
    raw = (repo or "").strip()
    deploy_key = Path(
        os.environ.get(
            "MINEBOX_UPDATE_DEPLOY_KEY",
            "/home/minebox/.ssh/minebox_update",
        )
    )
    if not raw or not deploy_key.is_file():
        return raw
    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "https://www.github.com/",
    ):
        if raw.lower().startswith(prefix):
            path = raw[len(prefix) :].removesuffix(".git").strip("/")
            if path:
                return f"git@github.com:{path}.git"
            break
    return raw


def paths(dev: bool) -> dict[str, Path]:
    if dev:
        status_file = Path(
            os.environ.get(
                "MINEBOX_UPDATE_STATUS_FILE",
                "runtime/updates/update-status.json",
            )
        )
        log_file = Path(
            os.environ.get(
                "MINEBOX_UPDATE_LOG_FILE",
                "runtime/updates/update.log",
            )
        )
        commit_file = Path(
            os.environ.get(
                "MINEBOX_UPDATE_COMMIT_FILE",
                "runtime/updates/installed-commit",
            )
        )
        work = Path(
            os.environ.get(
                "MINEBOX_UPDATE_WORK",
                str(Path(os.environ.get("MINEBOX_REPOSITORY_DIR", ".")).resolve() / "runtime" / "updates"),
            )
        )
        target = Path(
            os.environ.get("MINEBOX_UPDATE_TARGET", ".")
        ).resolve()
        return {
            "status": status_file.resolve(),
            "log": log_file.resolve(),
            "commit": commit_file.resolve(),
            "stage": (work / "stage").resolve(),
            "next": (work / "next").resolve(),
            "target": target,
            "previous": (work / "previous-app").resolve(),
        }

    return {
        "status": Path("/var/lib/minebox/update-status.json"),
        "log": Path("/var/log/minebox/update.log"),
        "commit": Path("/var/lib/minebox/installed-commit"),
        "stage": Path("/var/lib/minebox/updates/stage"),
        "next": Path("/var/lib/minebox/updates/next"),
        "target": Path("/opt/minebox"),
        "previous": Path("/opt/minebox.previous"),
    }


def write_commit(path: Path, commit: str) -> None:
    ensure_parent(path)
    path.write_text(commit + "\n", encoding="utf-8")


def _file_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def install_hotspot_helpers(target: Path, dev: bool) -> None:
    """Install captive portal + refresh hostapd/dnsmasq defaults for setup Wi-Fi."""
    if dev:
        return

    captive_script = target / "scripts" / "minebox_captive.py"
    if captive_script.is_file():
        run(["chmod", "0755", str(captive_script)])

    captive_unit = target / "services" / "minebox-captive.service"
    if captive_unit.is_file():
        run(
            [
                "install",
                "-m",
                "0644",
                str(captive_unit),
                "/etc/systemd/system/minebox-captive.service",
            ]
        )

    restart_units: list[str] = []

    hostapd_src = target / "services" / "hotspot" / "hostapd.conf"
    hostapd_dst = Path("/etc/hostapd/hostapd.conf")
    if hostapd_src.is_file():
        # hostapd treats CR as part of values; Windows checkouts break the AP.
        raw = hostapd_src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        current = _file_bytes(hostapd_dst)
        if current != raw:
            hostapd_dst.parent.mkdir(parents=True, exist_ok=True)
            hostapd_dst.write_bytes(raw)
            os.chmod(hostapd_dst, 0o644)
            restart_units.append("hostapd.service")

    # SoftAP client drops are common when brcmfmac leaves power-save on.
    # Prefer dynamic render (resolved SoftAP iface) over hard-coded wlan0.
    render_script = target / "scripts" / "minebox_render_hotspot_configs.py"
    if render_script.is_file():
        subprocess.run(
            ["/usr/bin/python3", str(render_script)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PYTHONPATH": str(target), "MINEBOX_APP_DIR": str(target)},
        )
        if "hostapd.service" not in restart_units:
            restart_units.append("hostapd.service")
    else:
        dropin_dir = Path("/etc/systemd/system/hostapd.service.d")
        dropin_dir.mkdir(parents=True, exist_ok=True)
        dropin = dropin_dir / "minebox.conf"
        dropin_body = (
            "[Unit]\n"
            "After=systemd-networkd.service\n"
            "Wants=systemd-networkd.service\n"
            "\n"
            "[Service]\n"
            "ExecStartPre=/usr/sbin/rfkill unblock wifi\n"
            "ExecStartPost=/bin/sh -c '/sbin/iwconfig wlan0 power off 2>/dev/null || "
            "/usr/sbin/iw dev wlan0 set power_save off 2>/dev/null || true'\n"
            "Restart=on-failure\n"
            "RestartSec=3\n"
        )
        previous_dropin = _file_bytes(dropin)
        dropin.write_text(dropin_body, encoding="utf-8")
        if previous_dropin != dropin_body.encode("utf-8"):
            if "hostapd.service" not in restart_units:
                restart_units.append("hostapd.service")

    dnsmasq_src = target / "services" / "hotspot" / "dnsmasq-minebox.conf"
    dnsmasq_dst = Path("/etc/dnsmasq.d/minebox.conf")
    dnsmasq_needs_bounce = False
    if dnsmasq_src.is_file():
        raw = dnsmasq_src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if _file_bytes(dnsmasq_dst) != raw:
            dnsmasq_dst.parent.mkdir(parents=True, exist_ok=True)
            dnsmasq_dst.write_bytes(raw)
            os.chmod(dnsmasq_dst, 0o644)
            dnsmasq_needs_bounce = True

    # Keep mDNS off SoftAP so hotspot clients are not pointed at the LAN IP.
    avahi_script = target / "scripts" / "minebox_install_avahi.py"
    if avahi_script.is_file():
        subprocess.run(
            ["/usr/bin/python3", str(avahi_script), "--port", "25565"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    # Keep dnsmasq as Type=simple without Debian resolvconf hooks (those hang).
    dnsmasq_dropin_src = (
        target / "services" / "hotspot" / "dnsmasq-minebox.service.dropin"
    )
    dnsmasq_dropin_dir = Path("/etc/systemd/system/dnsmasq.service.d")
    dnsmasq_dropin_dir.mkdir(parents=True, exist_ok=True)
    dnsmasq_dropin = dnsmasq_dropin_dir / "minebox.conf"
    safe_dropin = (
        "[Service]\n"
        "Type=simple\n"
        "ExecStartPre=\n"
        "ExecStartPost=\n"
        "ExecStart=\n"
        "ExecStart=/usr/sbin/dnsmasq -k "
        "--conf-file=/etc/dnsmasq.conf "
        "--conf-dir=/etc/dnsmasq.d,.dpkg-dist,.dpkg-old,.dpkg-new\n"
    ).encode()
    if dnsmasq_dropin_src.is_file():
        raw = (
            dnsmasq_dropin_src.read_bytes()
            .replace(b"\r\n", b"\n")
            .replace(b"\r", b"\n")
        )
    else:
        raw = safe_dropin
    if _file_bytes(dnsmasq_dropin) != raw:
        dnsmasq_dropin.write_bytes(raw)
        os.chmod(dnsmasq_dropin, 0o644)
        dnsmasq_needs_bounce = True
    # Always ensure the drop-in exists even if conf unchanged.
    elif not dnsmasq_dropin.is_file():
        dnsmasq_dropin.write_bytes(raw)
        os.chmod(dnsmasq_dropin, 0o644)
        dnsmasq_needs_bounce = True

    # Hotspot internet sharing: NAT + forward. Without these, clients get
    # "No internet" / DNS failures even though the Pi itself is online.
    nft_src = target / "services" / "hotspot" / "minebox-hotspot.nft"
    nft_dst = Path("/etc/nftables.conf")
    if nft_src.is_file():
        raw = nft_src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if _file_bytes(nft_dst) != raw:
            nft_dst.write_bytes(raw)
            os.chmod(nft_dst, 0o644)
        subprocess.run(
            ["systemctl", "enable", "--now", "nftables.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Always reload so a flushed ruleset is restored on update.
        subprocess.run(
            ["nft", "-f", str(nft_dst)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    sysctl_src = target / "services" / "hotspot" / "90-minebox-router.conf"
    sysctl_dst = Path("/etc/sysctl.d/90-minebox-router.conf")
    if sysctl_src.is_file():
        raw = sysctl_src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if _file_bytes(sysctl_dst) != raw:
            sysctl_dst.parent.mkdir(parents=True, exist_ok=True)
            sysctl_dst.write_bytes(raw)
            os.chmod(sysctl_dst, 0o644)
    subprocess.run(
        ["sysctl", "-w", "net.ipv4.ip_forward=1"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    # Apply iface-specific sysctl from rendered file when present (avoids wlan0 hard-code).
    subprocess.run(
        ["sysctl", "--system"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    subprocess.run(
        ["sysctl", "-w", "net.ipv4.conf.all.rp_filter=0"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    ssh_dropin_src = target / "services" / "hotspot" / "50-minebox-ssh.conf"
    if ssh_dropin_src.is_file():
        raw = ssh_dropin_src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        ssh_dir = Path("/etc/ssh/sshd_config.d")
        ssh_dir.mkdir(parents=True, exist_ok=True)
        ssh_dst = ssh_dir / "50-minebox.conf"
        if _file_bytes(ssh_dst) != raw:
            ssh_dst.write_bytes(raw)
            os.chmod(ssh_dst, 0o644)
            subprocess.run(
                ["systemctl", "try-reload-or-restart", "ssh.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            subprocess.run(
                ["systemctl", "try-reload-or-restart", "sshd.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

    run(["systemctl", "daemon-reload"], timeout=60)
    soft_systemctl(["enable", "--now", "minebox-captive.service"], timeout=30)
    # Always refresh captive (port 80 front-door); only bounce AP/DHCP when conf changed.
    soft_systemctl(["try-restart", "minebox-captive.service"], timeout=20)
    for unit in restart_units:
        if unit == "dnsmasq.service":
            continue
        soft_systemctl(["try-restart", unit], timeout=20)
    if dnsmasq_needs_bounce or "dnsmasq.service" in restart_units:
        restart_dnsmasq_safe()
    # If dnsmasq conf/drop-in already matched but service is dead, revive it.
    elif subprocess.run(
        ["systemctl", "is-active", "--quiet", "dnsmasq.service"],
        check=False,
        timeout=10,
    ).returncode != 0:
        restart_dnsmasq_safe()


def install_systemd_units(target: Path, dev: bool) -> None:
    """Refresh MineBox unit files from the installed app tree."""
    if dev:
        return
    units = [
        "minebox-api.service",
        "minebox-update.service",
        "minebox-maintenance.service",
        "minebox-maintenance.timer",
        "minebox-captive.service",
    ]
    for name in units:
        source = target / "services" / name
        if not source.is_file():
            continue
        run(
            [
                "install",
                "-m",
                "0644",
                str(source),
                f"/etc/systemd/system/{name}",
            ]
        )

    # Keep minecraft.service TimeoutStartSec and launcher path current.
    minecraft_unit_candidates = [
        target.parent / "systemd" / "minecraft.service",
        target / "services" / "minecraft.service",
    ]
    for source in minecraft_unit_candidates:
        if source.is_file():
            run(
                [
                    "install",
                    "-m",
                    "0644",
                    str(source),
                    "/etc/systemd/system/minecraft.service",
                ]
            )
            break

    run(["systemctl", "daemon-reload"], timeout=60)
    subprocess.run(
        ["systemctl", "enable", "--now", "minebox-maintenance.timer"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def install_networkmanager_polkit(target: Path, dev: bool) -> None:
    """Allow the minebox user to control NetworkManager from the dashboard."""
    if dev:
        return
    source = target / "services" / "polkit" / "10-minebox-networkmanager.rules"
    if not source.is_file():
        return
    destination = Path("/etc/polkit-1/rules.d/10-minebox-networkmanager.rules")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        os.chmod(destination, 0o644)
    except OSError as exc:
        print(f"warning: could not install NetworkManager polkit rule: {exc}", flush=True)
        return
    subprocess.run(
        ["systemctl", "try-reload-or-restart", "polkit.service"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def ensure_two_button_nav_config() -> None:
    """Keep encoder off and restore classic button actions until Seesaw ships."""
    path = Path("/etc/minebox/hardware.toml")
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"warning: could not read {path}: {exc}", flush=True)
        return

    section = ""
    changed = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
            out.append(line)
            continue
        if section == "[encoder]":
            if stripped.startswith("enabled"):
                if "false" not in stripped.lower():
                    changed = True
                out.append("enabled = false")
                continue
            if stripped.startswith("status"):
                out.append('status = "NOT_CONFIGURED"')
                changed = True
                continue
        if section == "[buttons.left]":
            if stripped.startswith("short_action"):
                out.append('short_action = "prev"')
                changed = True
                continue
            if stripped.startswith("long_action"):
                out.append('long_action = "back"')
                changed = True
                continue
        if section == "[buttons.right]":
            if stripped.startswith("short_action"):
                out.append('short_action = "next"')
                changed = True
                continue
            if stripped.startswith("long_action"):
                out.append('long_action = "select"')
                changed = True
                continue
        out.append(line)

    if not changed:
        return
    try:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"Updated {path}: encoder disabled, two-button nav restored.", flush=True)
    except OSError as exc:
        print(f"warning: could not write {path}: {exc}", flush=True)


def install_minecraft_permissions(target: Path, dev: bool) -> None:
    """Make /opt/minecraft writable by the minebox dashboard user."""
    if dev:
        return
    ensure_two_button_nav_config()
    install_networkmanager_polkit(target, dev)
    script = target / "scripts" / "minebox_fix_minecraft_perms.py"
    if script.is_file():
        run(["chmod", "0755", str(script)])
        run(["/usr/bin/python3", str(script)], timeout=300)
        run(
            [
                "install",
                "-m",
                "0755",
                str(script),
                "/usr/local/sbin/minebox-fix-minecraft-perms",
            ]
        )

    avahi_script = target / "scripts" / "minebox_install_avahi.py"
    if avahi_script.is_file():
        run(["chmod", "0755", str(avahi_script)])
        run(
            [
                "install",
                "-m",
                "0755",
                str(avahi_script),
                "/usr/local/sbin/minebox-install-avahi",
            ]
        )

    java_script = target / "scripts" / "minebox_ensure_java.py"
    if java_script.is_file():
        run(["chmod", "0755", str(java_script)])
        run(
            [
                "install",
                "-m",
                "0755",
                str(java_script),
                "/usr/local/sbin/minebox-ensure-java",
            ]
        )
        # Preinstall Java 8 during OTA — Bookworm has no apt package and Forge
        # 1.12 needs it. Other majors install on demand via sudo / ExecStartPre.
        print("Ensuring Java 8 runtime for legacy Forge...", flush=True)
        subprocess.run(
            ["/usr/bin/python3", str(java_script), "--min", "8", "--max", "8"],
            check=False,
            timeout=900,
        )

    java_active = target / "scripts" / "minebox_ensure_java_for_active.py"
    if java_active.is_file():
        run(["chmod", "0755", str(java_active)])

    tls_script = target / "scripts" / "minebox_ensure_tls.py"
    if tls_script.is_file():
        run(["chmod", "0755", str(tls_script)])
        run(
            [
                "install",
                "-m",
                "0755",
                str(tls_script),
                "/usr/local/sbin/minebox-ensure-tls",
            ]
        )
    api_run = target / "scripts" / "minebox_api_run.py"
    if api_run.is_file():
        run(["chmod", "0755", str(api_run)])

    fan_script = target / "scripts" / "minebox_fan_test.py"
    if fan_script.is_file():
        try:
            raw = fan_script.read_bytes().replace(b"\r\n", b"\n")
            fan_script.write_bytes(raw)
        except OSError:
            pass
        run(["chmod", "0755", str(fan_script)])
        run(
            [
                "install",
                "-m",
                "0755",
                str(fan_script),
                "/usr/local/sbin/minebox-fan-test",
            ]
        )

    # Ensure Pi 5 official cooler firmware control is enabled.
    for config_path in (
        Path("/boot/firmware/config.txt"),
        Path("/boot/config.txt"),
    ):
        if not config_path.is_file():
            continue
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "dtparam=cooling_fan=on" not in text:
            with config_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    "\n# MineBox: enable official Pi 5 Active Cooler control\n"
                    "dtparam=cooling_fan=on\n"
                )
            print(f"Enabled cooling_fan in {config_path}", flush=True)
        break

    # Allow the dashboard user to read live Minecraft service logs.
    subprocess.run(
        ["usermod", "-aG", "systemd-journal", "minebox"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # LAN discovery (.local) + optional UPnP helper for internet joins.
    subprocess.run(
        [
            "apt-get",
            "install",
            "-y",
            "avahi-daemon",
            "libnss-mdns",
            "miniupnpc",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if avahi_script.is_file():
        run(["/usr/bin/python3", str(avahi_script), "--port", "25565"], timeout=30)
        subprocess.run(
            ["systemctl", "enable", "--now", "avahi-daemon.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

    # Canonical sudoers from app tree (Checkpoint 7 — avoid drift with install.sh / pi-gen).
    sudoers = Path("/etc/sudoers.d/minebox")
    sudoers_src = target / "services" / "sudoers" / "minebox"
    desired = ""
    current = ""
    try:
        if sudoers_src.is_file():
            desired = sudoers_src.read_text(encoding="utf-8")
            if not desired.endswith("\n"):
                desired += "\n"
        else:
            print("warning: missing services/sudoers/minebox; leaving sudoers unchanged", flush=True)
        if sudoers.is_file():
            current = sudoers.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"warning: could not sync sudoers: {exc}", flush=True)
        desired = ""
    if desired and current.strip() != desired.strip():
        try:
            sudoers.write_text(desired, encoding="utf-8")
            os.chmod(sudoers, 0o440)
            check = subprocess.run(
                ["visudo", "-cf", str(sudoers)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if check.returncode == 0:
                print("Synced /etc/sudoers.d/minebox from app tree.", flush=True)
            else:
                print(
                    "warning: sudoers validation failed: "
                    + (check.stderr or check.stdout or ""),
                    flush=True,
                )
        except OSError as exc:
            print(f"warning: could not write sudoers: {exc}", flush=True)

    # Re-render SoftAP configs after update (idempotent; preserves resolved iface).
    render_script = target / "scripts" / "minebox_render_hotspot_configs.py"
    if render_script.is_file():
        subprocess.run(
            ["/usr/bin/python3", str(render_script)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PYTHONPATH": str(target)},
        )


def preserve_persistent_state(previous: Path, target: Path, log_file: Path) -> None:
    """Keep admin auth and similar state across /opt/minebox swaps."""
    durable = Path("/var/lib/minebox")
    durable.mkdir(parents=True, exist_ok=True)

    candidates = [
        previous / "config" / "auth.json",
        previous / "auth.json",
        Path("/opt/minebox.previous/config/auth.json"),
        Path("/opt/minebox/config/auth.json"),
    ]
    durable_auth = durable / "auth.json"
    if not durable_auth.is_file():
        for source in candidates:
            if not source.is_file():
                continue
            try:
                shutil.copy2(source, durable_auth)
                os.chmod(durable_auth, 0o600)
                try:
                    shutil.chown(durable_auth, user="minebox", group="minebox")
                except OSError:
                    pass
                log(log_file, f"Preserved admin credentials from {source}.")
                break
            except OSError as exc:
                log(log_file, f"Could not preserve auth from {source}: {exc}")

    # Also restore a copy into the new app tree for compatibility.
    if durable_auth.is_file():
        try:
            destination = target / "config" / "auth.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(durable_auth, destination)
            os.chmod(destination, 0o600)
            try:
                shutil.chown(destination, user="minebox", group="minebox")
                shutil.chown(destination.parent, user="minebox", group="minebox")
            except OSError:
                pass
        except OSError as exc:
            log(log_file, f"Could not mirror auth into new app tree: {exc}")


def restart_api(dev: bool) -> None:
    if dev:
        return
    run(["systemctl", "restart", "minebox-api.service"], timeout=120)


def ensure_api_running(dev: bool, log_file: Path | None = None) -> None:
    """Best-effort: never leave the dashboard permanently stopped after OTA."""
    if dev:
        return
    try:
        soft_systemctl(["start", "minebox-api.service"], timeout=120)
        active = subprocess.run(
            ["systemctl", "is-active", "minebox-api.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if (active.stdout or "").strip() != "active":
            soft_systemctl(["restart", "minebox-api.service"], timeout=120)
    except Exception as exc:  # noqa: BLE001
        if log_file is not None:
            log(log_file, f"WARNING: could not ensure minebox-api is running: {exc}")


def stop_api(dev: bool) -> None:
    if dev:
        return
    subprocess.run(
        ["systemctl", "stop", "minebox-api.service"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def apply_update(dev: bool) -> int:
    locations = paths(dev)
    status_file = locations["status"]
    log_file = locations["log"]
    commit_file = locations["commit"]
    stage = locations["stage"]
    next_dir = locations["next"]
    target = locations["target"]
    previous = locations["previous"]

    repo = effective_repo_url(cfg("repo", DEFAULT_REPO))
    branch = cfg("branch", DEFAULT_BRANCH)
    configured_subdir = cfg("app_subdir", DEFAULT_APP_SUBDIR)
    old_commit = None
    if commit_file.is_file():
        old_commit = commit_file.read_text(encoding="utf-8").strip() or None

    swapped = False
    new_commit = None
    api_stopped = False

    try:
        status(
            status_file,
            "updating",
            "Downloading the MineBox update from GitHub.",
            old_commit=old_commit,
        )
        log(log_file, f"Cloning {repo} branch {branch}.")

        ensure_parent(stage)
        safe_remove(stage)
        run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--no-tags",
                "--single-branch",
                "--branch",
                branch,
                repo,
                str(stage),
            ],
            env=git_env(),
        )

        target_commit = os.environ.get("MINEBOX_UPDATE_TARGET_COMMIT", "").strip()
        if target_commit:
            run(
                ["git", "-C", str(stage), "fetch", "--depth", "1", "origin", target_commit],
                env=git_env(),
            )
            run(
                ["git", "-C", str(stage), "checkout", "--detach", target_commit],
                env=git_env(),
            )

        new_commit = run(
            ["git", "-C", str(stage), "rev-parse", "HEAD"],
            env=git_env(),
        ).stdout.strip()

        status(
            status_file,
            "validating",
            "Validating the downloaded MineBox release.",
            old_commit=old_commit,
            new_commit=new_commit,
        )
        app_dir = resolve_app_dir(stage, configured_subdir)
        validate_app(app_dir)
        builder_root = app_dir.parent if app_dir.name == "app" else stage
        copy_app_tree(app_dir, next_dir, builder_root)

        status(
            status_file,
            "switching",
            "Switching MineBox to the new release.",
            old_commit=old_commit,
            new_commit=new_commit,
        )
        log(log_file, f"Installing update into {target}.")

        stop_api(dev)
        api_stopped = True

        if target.exists() or target.is_symlink():
            safe_remove(previous)
            if dev:
                # Keep a backup copy for rollback; do not move the live tree
                # away while the development server may still be reading it.
                if previous.exists():
                    safe_remove(previous)
                shutil.copytree(target, previous, dirs_exist_ok=False)
                # Replace live files in place.
                for child in target.iterdir():
                    if child.name in {"runtime", ".venv"}:
                        continue
                    safe_remove(child)
                for child in next_dir.iterdir():
                    destination = target / child.name
                    if child.is_dir():
                        shutil.copytree(child, destination)
                    else:
                        shutil.copy2(child, destination)
            else:
                target.replace(previous)
                next_dir.replace(target)
                swapped = True
                try:
                    shutil.chown(target, user="minebox", group="minebox")
                    for path in target.rglob("*"):
                        try:
                            shutil.chown(path, user="minebox", group="minebox")
                        except OSError:
                            pass
                except OSError:
                    pass
        else:
            next_dir.replace(target)
            swapped = True

        if previous.exists():
            preserve_persistent_state(previous, target, log_file)
        else:
            preserve_persistent_state(target, target, log_file)

        requirements = target / "requirements.txt"
        if requirements.is_file() and not dev:
            log(log_file, "Installing Python requirements.")
            # Soft-fail: never brick the dashboard over an optional pip package.
            try:
                pip_result = subprocess.run(
                    [
                        "pip3",
                        "install",
                        "--break-system-packages",
                        "-r",
                        str(requirements),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=900,
                )
                if pip_result.returncode != 0:
                    detail = (pip_result.stderr or pip_result.stdout or "").strip()
                    log(
                        log_file,
                        "WARNING: pip install reported errors (continuing): "
                        + detail[:2000],
                    )
            except Exception as pip_exc:  # noqa: BLE001
                log(log_file, f"WARNING: pip install skipped after error: {pip_exc}")

        install_systemd_units(target, dev)
        install_minecraft_permissions(target, dev)
        install_hotspot_helpers(target, dev)
        restart_api(dev)
        api_stopped = False
        health_url = os.environ.get(
            "MINEBOX_HEALTH_URL",
            "http://127.0.0.1:8080/api/v1/health",
        )
        # Allow extra time after pip + systemd restart.
        if not dev and not healthy(health_url, timeout=120):
            raise RuntimeError("The updated dashboard failed its health check.")

        write_commit(commit_file, new_commit)
        status(
            status_file,
            "success",
            "MineBox was updated successfully.",
            old_commit=old_commit,
            new_commit=new_commit,
            rollback_available=previous.exists(),
        )
        log(log_file, f"Update completed: {old_commit} -> {new_commit}")
        safe_remove(stage)
        if not swapped:
            safe_remove(next_dir)
        return 0

    except Exception as exc:  # noqa: BLE001 - must always write failure status
        message = str(exc) or exc.__class__.__name__
        log(log_file, f"Update failed: {message}")
        if swapped and previous.exists():
            try:
                log(log_file, "Rolling back to the previous MineBox release.")
                failed = target.with_name(target.name + ".failed")
                safe_remove(failed)
                if target.exists():
                    target.replace(failed)
                previous.replace(target)
                restart_api(dev)
                api_stopped = False
                rollback_ok = healthy(
                    os.environ.get(
                        "MINEBOX_HEALTH_URL",
                        "http://127.0.0.1:8080/api/v1/health",
                    ),
                    timeout=120,
                )
                status(
                    status_file,
                    "rolled_back" if rollback_ok else "failed",
                    (
                        "Update failed and MineBox was restored: "
                        if rollback_ok
                        else "Update failed and rollback did not fully recover: "
                    )
                    + message,
                    old_commit=old_commit,
                    new_commit=new_commit,
                    rollback_succeeded=rollback_ok,
                )
            except Exception as rollback_exc:  # noqa: BLE001
                status(
                    status_file,
                    "failed",
                    f"Update failed: {message}. Rollback also failed: {rollback_exc}",
                    old_commit=old_commit,
                    new_commit=new_commit,
                    rollback_succeeded=False,
                )
        else:
            status(
                status_file,
                "failed",
                message,
                old_commit=old_commit,
                new_commit=new_commit,
                rollback_succeeded=None,
            )
        return 1
    finally:
        # Critical: never leave minebox-api stopped after an update attempt.
        if api_stopped:
            log(log_file, "Ensuring minebox-api is started after update attempt.")
        ensure_api_running(dev, log_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a MineBox GitHub update.")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Apply into the local development app directory.",
    )
    args = parser.parse_args()
    return apply_update(dev=args.dev)


if __name__ == "__main__":
    raise SystemExit(main())
