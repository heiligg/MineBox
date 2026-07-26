#!/usr/bin/python3
"""Ensure /opt/minecraft is owned by minebox so the dashboard can edit servers.

Runs as root from minebox-api ExecStartPre and from the update apply path.
Safe to call repeatedly; skips work when ownership is already correct.
"""
from __future__ import annotations

import os
import pwd
import grp
import subprocess
import sys
from pathlib import Path


DEFAULT_ROOT = Path("/opt/minecraft")
OWNER = "minebox"
GROUP = "minebox"


def _ids() -> tuple[int, int]:
    return pwd.getpwnam(OWNER).pw_uid, grp.getgrnam(GROUP).gr_gid


def _needs_fix(path: Path, uid: int, gid: int) -> bool:
    try:
        st = path.stat()
    except OSError:
        return False
    return st.st_uid != uid or st.st_gid != gid


def fix_tree(root: Path) -> int:
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)

    uid, gid = _ids()
    changed = 0

    # Ensure standard layout exists.
    for relative in ("servers", "metadata", "backups"):
        (root / relative).mkdir(parents=True, exist_ok=True)

    for path in [root, *root.rglob("*")]:
        try:
            if _needs_fix(path, uid, gid):
                os.chown(path, uid, gid, follow_symlinks=False)
                changed += 1
            if path.is_dir():
                mode = path.stat().st_mode
                # setgid so new files inherit the minebox group
                desired = 0o2770
                if (mode & 0o7777) != desired:
                    path.chmod(desired)
                    changed += 1
        except OSError as exc:
            print(f"warning: {path}: {exc}", file=sys.stderr)

    # Best-effort ACLs so both minebox and minecraft users can collaborate.
    try:
        subprocess.run(
            [
                "setfacl",
                "-R",
                "-m",
                "u:minebox:rwX,u:minecraft:rwX,g:minebox:rwX,m::rwX",
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        subprocess.run(
            [
                "setfacl",
                "-R",
                "-d",
                "-m",
                "u:minebox:rwX,u:minecraft:rwX,g:minebox:rwX,m::rwX",
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        pass

    return changed


def main() -> int:
    root = Path(os.environ.get("MINEBOX_MINECRAFT_ROOT", str(DEFAULT_ROOT)))
    if os.geteuid() != 0:
        # Non-root: try to chown what we own; escalate note otherwise.
        try:
            uid, gid = _ids()
            if root.exists() and _needs_fix(root, uid, gid):
                print(
                    "error: must run as root to fix Minecraft ownership "
                    f"under {root}",
                    file=sys.stderr,
                )
                return 1
        except KeyError as exc:
            print(f"error: missing user/group: {exc}", file=sys.stderr)
            return 1

    try:
        changed = fix_tree(root)
    except KeyError as exc:
        print(f"error: missing user/group: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Minecraft permissions OK under {root} ({changed} changes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
