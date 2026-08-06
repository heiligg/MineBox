#!/usr/bin/python3
"""Ensure Java for the active MineBox server (runs as root from systemd ExecStartPre).

Uses the same version→Java mapping as the launcher so Forge 1.12 gets Java 8,
modern loaders get 17/21, etc. Safe to call repeatedly.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

APP_DIR = Path(os.environ.get("MINEBOX_APP_DIR", "/opt/minebox")).resolve()
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _load_ensure_java():
    path = APP_DIR / "scripts" / "minebox_ensure_java.py"
    spec = importlib.util.spec_from_file_location("minebox_ensure_java", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    from services import servers
    from services.launcher import _max_java_major, _required_java_major

    instance = servers.active_server()
    if instance is None:
        print("No active Minecraft server; skipping Java ensure.", file=sys.stderr)
        return 0

    server_dir = Path(instance.directory)
    required = _required_java_major(instance.version, server_dir=server_dir)
    maximum = _max_java_major(instance.version, loader=instance.loader)
    if maximum is not None and required > maximum:
        required = maximum

    print(
        f"Ensuring Java for '{instance.name}' "
        f"(MC {instance.version} / {instance.loader}: need {required}"
        + (f"-{maximum}" if maximum is not None else "+")
        + ")...",
        flush=True,
    )
    ensure_java = _load_ensure_java()
    java = ensure_java.ensure(required, maximum)
    print(f"Java ready: {java}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"Java ensure for active server failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
