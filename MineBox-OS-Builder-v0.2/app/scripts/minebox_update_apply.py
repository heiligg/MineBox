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


def healthy(url: str, timeout: int = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if 200 <= int(response.status) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
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
            "-o BatchMode=yes"
        )
    return env


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


def install_systemd_units(target: Path, dev: bool) -> None:
    """Refresh MineBox unit files from the installed app tree."""
    if dev:
        return
    units = [
        "minebox-api.service",
        "minebox-update.service",
        "minebox-maintenance.service",
        "minebox-maintenance.timer",
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
    run(["systemctl", "daemon-reload"], timeout=60)


def install_minecraft_permissions(target: Path, dev: bool) -> None:
    """Make /opt/minecraft writable by the minebox dashboard user."""
    if dev:
        return
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

    sudoers = Path("/etc/sudoers.d/minebox")
    desired = (
        "minebox ALL=(root) NOPASSWD: "
        "/usr/bin/systemctl start minecraft.service, "
        "/usr/bin/systemctl stop minecraft.service, "
        "/usr/bin/systemctl restart minecraft.service, "
        "/usr/bin/systemctl start minebox-update.service, "
        "/usr/bin/python3 /opt/minebox/scripts/minebox_fix_minecraft_perms.py, "
        "/usr/local/sbin/minebox-fix-minecraft-perms, "
        "/usr/bin/systemctl poweroff, "
        "/usr/bin/systemctl reboot\n"
    )
    try:
        current = sudoers.read_text(encoding="utf-8") if sudoers.is_file() else ""
    except OSError:
        current = ""
    if "minebox_fix_minecraft_perms" not in current:
        sudoers.write_text(desired, encoding="utf-8")
        os.chmod(sudoers, 0o440)
        subprocess.run(
            ["visudo", "-cf", str(sudoers)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )


def restart_api(dev: bool) -> None:
    if dev:
        return
    run(["systemctl", "restart", "minebox-api.service"], timeout=120)


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

    repo = cfg("repo", DEFAULT_REPO)
    branch = cfg("branch", DEFAULT_BRANCH)
    configured_subdir = cfg("app_subdir", DEFAULT_APP_SUBDIR)
    old_commit = None
    if commit_file.is_file():
        old_commit = commit_file.read_text(encoding="utf-8").strip() or None

    swapped = False
    new_commit = None

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

        requirements = target / "requirements.txt"
        if requirements.is_file() and not dev:
            log(log_file, "Installing Python requirements.")
            run(
                [
                    "pip3",
                    "install",
                    "--break-system-packages",
                    "-r",
                    str(requirements),
                ],
                timeout=900,
            )

        install_systemd_units(target, dev)
        install_minecraft_permissions(target, dev)
        restart_api(dev)
        health_url = os.environ.get(
            "MINEBOX_HEALTH_URL",
            "http://127.0.0.1:8080/api/v1/health",
        )
        if not dev and not healthy(health_url):
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
                rollback_ok = healthy(
                    os.environ.get(
                        "MINEBOX_HEALTH_URL",
                        "http://127.0.0.1:8080/api/v1/health",
                    )
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
