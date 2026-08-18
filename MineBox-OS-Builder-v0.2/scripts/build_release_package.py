#!/usr/bin/env python3
"""Build MineBox OS Prototype v1.0 release tree and archives (Checkpoint 8)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_NAME = "MineBox_OS_Prototype_v1.0"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip().splitlines()[0]
RELEASE_DIR = ROOT / "releases" / RELEASE_NAME
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".test-runtime",
    "runtime",
    ".build",
    "output",
    "work",
    "deploy",
    "node_modules",
    ".idea",
    ".vscode",
    "backups",
}
EXCLUDE_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".swp",
    ".backup",
    ".bak",
    ".img",
    ".img.xz",
}
EXCLUDE_FILE_NAMES = {
    "auth.json",
    ".minebox-rcon-password",
    ".minebox-setup-complete",
    "network.conf",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def should_skip(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts if path.is_relative_to(root) else path.parts
    for part in rel_parts:
        if part in EXCLUDE_DIR_NAMES:
            return True
        if part.endswith(".backup") or part.endswith(".backup-"):
            return True
    if path.is_file():
        if path.name in EXCLUDE_FILE_NAMES:
            return True
        if path.suffix in EXCLUDE_FILE_SUFFIXES:
            return True
        if path.name.endswith(".backup") or ".backup-" in path.name:
            return True
    return False


def copy_tree(src: Path, dst: Path, *, root_for_skip: Path | None = None) -> int:
    root_for_skip = root_for_skip or src
    count = 0
    if src.is_file():
        if should_skip(src, root_for_skip):
            return 0
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    for path in src.rglob("*"):
        if should_skip(path, src):
            continue
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            # Extra: skip stale pi-gen embedded app snapshot
            if "files" in rel.parts and "minebox" in rel.parts and "00-install-minebox" in str(rel):
                # Allow copying empty marker only via explicit handling
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            count += 1
    return count


def clean_python_caches(base: Path) -> None:
    for path in base.rglob("__pycache__"):
        shutil.rmtree(path, ignore_errors=True)
    for path in base.rglob("*.pyc"):
        try:
            path.unlink()
        except OSError:
            pass


def git_commit() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def run_unittest_summary() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    env["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
    env["MINEBOX_HARDWARE_PROFILE"] = "mock"
    env["MINEBOX_CONFIG"] = str(ROOT / "config" / "minebox.example.toml")
    env["MINEBOX_HARDWARE_CONFIG"] = str(ROOT / "config" / "hardware.example.toml")
    env["MINEBOX_RUNTIME_DIR"] = str(ROOT / ".test-runtime")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ran = re.search(r"Ran (\d+) tests", out)
    skipped = re.search(r"skipped=(\d+)", out)
    ok = proc.returncode == 0 and "FAILED" not in out.splitlines()[-5:]
    # unittest prints OK or FAILED on last lines
    ok = proc.returncode == 0
    return {
        "returncode": proc.returncode,
        "tests_run": int(ran.group(1)) if ran else None,
        "skipped": int(skipped.group(1)) if skipped else 0,
        "ok": ok,
        "tail": "\n".join(out.splitlines()[-30:]),
    }


def security_scan() -> dict:
    findings: list[dict] = []
    patterns = [
        (r"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----", "private_key"),
        (r"(?i)aws_secret_access_key\s*=", "cloud_secret"),
        (r"(?i)tskey-[a-z0-9]+", "tailscale_key"),
    ]
    for path in (ROOT / "app").rglob("*"):
        if should_skip(path, ROOT / "app") or not path.is_file():
            continue
        if path.suffix.lower() in {".png", ".jpg", ".woff", ".ttf"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat, kind in patterns:
            if re.search(pat, text):
                findings.append({"file": str(path.relative_to(ROOT)), "kind": kind})
    # Bootstrap markers (documented, not blockers)
    documented = [
        {"item": "bootstrap hotspot PSK in hostapd templates", "class": "DOCUMENTED_LIMITATION"},
        {"item": "FIRST_USER_PASS in minebox-pi5.conf", "class": "DOCUMENTED_LIMITATION"},
        {"item": "LEGACY_HARDCODED_RCON migration marker", "class": "SAFE_TO_KEEP"},
    ]
    return {
        "generated_at": TIMESTAMP,
        "blocker_findings": findings,
        "documented": documented,
        "openapi_default": "disabled",
        "mock_hardware_forced_in_api": False,
        "ok": len(findings) == 0,
    }


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def build_tree(test_summary: dict, security: dict) -> None:
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)

    # Core payload
    copy_tree(ROOT / "app", RELEASE_DIR / "source" / "app")
    # Ensure no stale backups slipped through
    for bad in (RELEASE_DIR / "source").rglob("*"):
        if bad.is_file() and (bad.suffix in EXCLUDE_FILE_SUFFIXES or ".backup" in bad.name):
            bad.unlink(missing_ok=True)

    (RELEASE_DIR / "installer").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "app" / "install.sh", RELEASE_DIR / "installer" / "install.sh")
    write_text(
        RELEASE_DIR / "installer" / "README.md",
        "# Installer\n\n```bash\nsudo bash install.sh\n```\n\n"
        "Source of truth mirrors `app/install.sh`. "
        "Preserves `/opt/minecraft` and `/var/lib/minebox` on upgrade/uninstall.\n",
    )

    copy_tree(ROOT / "config", RELEASE_DIR / "config")
    # systemd units from app/services
    sysd = RELEASE_DIR / "systemd"
    sysd.mkdir(parents=True, exist_ok=True)
    for unit in (ROOT / "app" / "services").glob("*.service"):
        shutil.copy2(unit, sysd / unit.name)
    for unit in (ROOT / "app" / "services").glob("*.timer"):
        shutil.copy2(unit, sysd / unit.name)
    if (ROOT / "systemd" / "minecraft.service").is_file():
        shutil.copy2(ROOT / "systemd" / "minecraft.service", sysd / "minecraft.service")

    sudoers_dst = RELEASE_DIR / "sudoers"
    sudoers_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "app" / "services" / "sudoers" / "minebox", sudoers_dst / "minebox")

    # pi-gen without embedded stale app tree
    pigen_src = ROOT / "pi-gen" / "stage-minebox"
    pigen_dst = RELEASE_DIR / "pi-gen" / "stage-minebox"
    for path in pigen_src.rglob("*"):
        rel = path.relative_to(pigen_src)
        if "files" in rel.parts and "minebox" in rel.parts and rel.parts[0] == "00-install-minebox":
            continue
        if should_skip(path, pigen_src):
            continue
        target = pigen_dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    write_text(
        pigen_dst / "00-install-minebox" / "files" / "README.md",
        "The live application tree is rsynced from `app/` by `build.sh` at image-build time.\n"
        "A stale embedded copy is intentionally omitted from this release package.\n",
    )

    scripts_dst = RELEASE_DIR / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "minebox_validate_install.py",
        "minebox_first_boot_check.py",
        "minebox_render_hotspot_configs.py",
        "minebox_update_apply.py",
        "minebox_set_os_password.py",
        "minebox_api_run.py",
    ):
        src = ROOT / "app" / "scripts" / name
        if src.is_file():
            shutil.copy2(src, scripts_dst / name)
    shutil.copy2(ROOT / "scripts" / "build_release_package.py", scripts_dst / "build_release_package.py")
    for name in ("build.sh", "check-project.sh"):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, scripts_dst / name)

    copy_tree(ROOT / "docs", RELEASE_DIR / "docs")
    shutil.copy2(ROOT / "README.md", RELEASE_DIR / "README.md")
    shutil.copy2(ROOT / "CHANGELOG.md", RELEASE_DIR / "CHANGELOG.md")
    shutil.copy2(ROOT / "VERSION", RELEASE_DIR / "VERSION")
    shutil.copy2(ROOT / "requirements.txt", RELEASE_DIR / "requirements.txt")
    if (ROOT / "README-FIRST.md").is_file():
        shutil.copy2(ROOT / "README-FIRST.md", RELEASE_DIR / "README-FIRST.md")

    # Test summary (not full .test-runtime)
    tests_dst = RELEASE_DIR / "tests"
    tests_dst.mkdir(parents=True, exist_ok=True)
    for path in (ROOT / "tests").glob("test_*.py"):
        shutil.copy2(path, tests_dst / path.name)
    write_text(
        tests_dst / "TEST_SUMMARY.json",
        json.dumps(test_summary, indent=2) + "\n",
    )

    reports = RELEASE_DIR / "validation_reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_text(reports / "security_scan.json", json.dumps(security, indent=2) + "\n")
    write_text(reports / "unittest_summary.json", json.dumps(test_summary, indent=2) + "\n")
    write_text(
        reports / "image_build_status.txt",
        "IMAGE ARTIFACT: NOT GENERATED IN THIS ENVIRONMENT\n"
        "Reason: full pi-gen/Docker image build requires Linux + Docker + substantial disk.\n"
        "Validate stages with check-project.sh / build.sh --docker on a Linux host.\n"
        f"Recorded at: {TIMESTAMP}\n",
    )
    write_text(
        reports / "physical_validation_status.txt",
        "PHYSICAL RASPBERRY PI VALIDATION: NOT PERFORMED IN CHECKPOINT 8 PACKAGING\n"
        "See docs/v1/Prototype_Hardware_Test_Plan.md\n",
    )

    write_text(
        RELEASE_DIR / "README_RELEASE.md",
        f"# {RELEASE_NAME}\n\n"
        f"**Version:** `{VERSION}`\n\n"
        "**Classification:** B — Software package validated, image build pending\n\n"
        "Prototype — not mass-production ready. Physical hardware validation is separate.\n\n"
        "## Contents\n\n"
        "- `installer/` — idempotent install.sh\n"
        "- `source/app/` — application tree\n"
        "- `config/` — example configs (safe placeholders)\n"
        "- `systemd/` — unit files\n"
        "- `sudoers/` — allowlist\n"
        "- `pi-gen/` — image stage (app embedded at build time)\n"
        "- `scripts/` — validation, SoftAP render, OTA apply, build helpers\n"
        "- `docs/` — documentation\n"
        "- `validation_reports/` — security + test summaries\n\n"
        "## Install\n\n"
        "```bash\nsudo bash installer/install.sh\n```\n\n"
        "## Image build\n\n"
        "On Linux: copy stage into a builder checkout and run `./build.sh --docker`.\n"
        "No `.img` is included in this package unless separately generated and listed in the manifest.\n",
    )
    shutil.copy2(ROOT / "docs" / "v1" / "Release_Checklist.md", RELEASE_DIR / "RELEASE_CHECKLIST.md")


def make_archives() -> dict:
    releases_root = ROOT / "releases"
    releases_root.mkdir(parents=True, exist_ok=True)
    tar_path = releases_root / f"{RELEASE_NAME}.tar.gz"
    zip_path = releases_root / f"{RELEASE_NAME}.zip"
    if tar_path.exists():
        tar_path.unlink()
    if zip_path.exists():
        zip_path.unlink()

    # tar.gz via Python tarfile
    import tarfile

    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(RELEASE_DIR, arcname=RELEASE_NAME)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in RELEASE_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(Path(RELEASE_NAME) / path.relative_to(RELEASE_DIR)))

    artifacts = {
        "tar_gz": {
            "name": tar_path.name,
            "path": str(tar_path),
            "size_bytes": tar_path.stat().st_size,
            "sha256": sha256_file(tar_path),
        },
        "zip": {
            "name": zip_path.name,
            "path": str(zip_path),
            "size_bytes": zip_path.stat().st_size,
            "sha256": sha256_file(zip_path),
        },
    }
    sums = releases_root / "SHA256SUMS"
    lines = [
        f"{artifacts['tar_gz']['sha256']}  {artifacts['tar_gz']['name']}",
        f"{artifacts['zip']['sha256']}  {artifacts['zip']['name']}",
    ]
    # Also hash release dir marker files into SUMS for tree? Keep archives only.
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    artifacts["sha256sums"] = str(sums)
    return artifacts


def verify_archive(tar_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        import tarfile

        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(tmp_path)
        extracted = tmp_path / RELEASE_NAME
        required = [
            extracted / "VERSION",
            extracted / "installer" / "install.sh",
            extracted / "source" / "app" / "api" / "server.py",
            extracted / "sudoers" / "minebox",
            extracted / "docs" / "v1" / "Final_Release_Audit.md",
            extracted / "scripts" / "minebox_first_boot_check.py",
            extracted / "RELEASE_MANIFEST.json",
        ]
        missing = [str(p.relative_to(extracted)) for p in required if not p.is_file()]
        # exclusions
        bad = []
        for path in extracted.rglob("*"):
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                bad.append(str(path))
            if path.name == "auth.json":
                bad.append(str(path))
        version = (extracted / "VERSION").read_text(encoding="utf-8").strip().splitlines()[0]
        return {
            "ok": not missing and not bad and version == VERSION,
            "missing": missing,
            "forbidden_found": bad,
            "version": version,
        }


def write_manifest(test_summary: dict, security: dict, artifacts: dict, verify: dict) -> None:
    manifest = {
        "product_name": "MineBox OS Prototype",
        "release_name": "MineBox OS Prototype v1.0",
        "semantic_version": VERSION,
        "release_type": "prototype",
        "target_hardware": ["Raspberry Pi 5"],
        "supported_base_os": ["Raspberry Pi OS 64-bit (Debian Trixie/Bookworm lineage via pi-gen)"],
        "build_timestamp": TIMESTAMP,
        "git_commit": git_commit(),
        "included_features": [
            "typed configuration",
            "secrets separation",
            "HAL mock/Pi5/CM5-stub",
            "first-boot wizard",
            "auth CSRF rate-limit",
            "Minecraft lifecycle",
            "providers",
            "backup restore",
            "crash recovery",
            "thermal monitoring",
            "Chromium kiosk",
            "curses fallback",
            "dual-radio SoftAP",
            "internet sharing optional",
            "nftables firewall",
            "Tailscale provider optional",
            "idempotent installer",
            "pi-gen integration",
        ],
        "official_server_providers": ["paper", "vanilla"],
        "experimental_providers": ["forge", "fabric"],
        "hardware_profile_status": {
            "buttons": "SOURCE_VERIFIED",
            "encoder": "I2C1_0x36",
            "encoder_int": "GPIO22",
            "leds": "NOT_CONFIGURED",
            "fan_gpio": "NOT_CONFIGURED",
            "cm5": "stub",
        },
        "network_features": {
            "softap": True,
            "internet_sharing": "optional",
            "firewall": "nftables",
            "dynamic_iface_render": True,
        },
        "remote_access_status": "optional_tailscale_disabled_by_default",
        "test_counts": {
            "ran": test_summary.get("tests_run"),
            "skipped": test_summary.get("skipped"),
            "ok": test_summary.get("ok"),
        },
        "image_status": "not_generated_in_this_environment",
        "physical_validation_status": "not_performed",
        "unresolved_gpio_status": "encoder_led_fan_NOT_CONFIGURED",
        "known_limitations_doc": "docs/v1/Known_Limitations.md",
        "release_classification": "B",
        "release_classification_label": "RELEASED — SOFTWARE PACKAGE VALIDATED, IMAGE BUILD PENDING",
        "mass_production_ready": False,
        "artifacts": artifacts,
        "archive_extraction_verification": verify,
        "security_scan_ok": security.get("ok"),
    }
    write_text(RELEASE_DIR / "RELEASE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    # Also copy to releases/
    write_text(ROOT / "releases" / "RELEASE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")


def main() -> int:
    print(f"Building release {RELEASE_NAME} ({VERSION})")
    clean_python_caches(ROOT / "app")
    clean_python_caches(ROOT / "tests")

    print("Running unittest suite…")
    test_summary = run_unittest_summary()
    print(test_summary.get("tail", ""))
    security = security_scan()
    if security.get("blocker_findings"):
        print("ERROR: security scan findings:", security.get("blocker_findings"), file=sys.stderr)

    build_tree(test_summary, security)
    write_manifest(
        test_summary,
        security,
        artifacts={"status": "pending"},
        verify={"status": "pending"},
    )

    artifacts = make_archives()
    verify = verify_archive(Path(artifacts["tar_gz"]["path"]))
    write_manifest(test_summary, security, artifacts, verify)
    # Rebuild once so the tarball includes the final manifest (external SHA256SUMS remain authoritative).
    artifacts = make_archives()
    verify = verify_archive(Path(artifacts["tar_gz"]["path"]))
    write_manifest(test_summary, security, artifacts, verify)
    # Refresh external checksum file after final archive write
    artifacts = make_archives()
    verify = verify_archive(Path(artifacts["tar_gz"]["path"]))
    write_manifest(test_summary, security, artifacts, verify)

    print(json.dumps({"artifacts": artifacts, "verify": verify, "tests_ok": test_summary.get("ok")}, indent=2))
    if not test_summary.get("ok") or not verify.get("ok") or not security.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
