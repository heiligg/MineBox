#!/usr/bin/env python3
"""Development launcher for the 800×480 MineBox display UI.

Usage (from MineBox-OS-Builder-v0.2):

  set PYTHONPATH=app
  set MINEBOX_FORCE_MOCK_HARDWARE=1
  python app/scripts/minebox_display_dev.py

Opens http://127.0.0.1:8080/display/dev in the default browser when possible,
or prints the URL. Keyboard: arrows = move, Enter = select, Esc = back,
[ ] = left/right button short, { } = holds.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"


def main() -> int:
    os.environ.setdefault("PYTHONPATH", str(APP))
    os.environ.setdefault("MINEBOX_FORCE_MOCK_HARDWARE", "1")
    os.environ.setdefault("MINEBOX_HARDWARE_PROFILE", "mock")
    os.environ.setdefault("MINEBOX_DEV_MODE", "1")
    os.environ.setdefault("MINEBOX_SKIP_FIRST_BOOT", "1")
    runtime = ROOT / ".dev-runtime"
    runtime.mkdir(exist_ok=True)
    os.environ.setdefault("MINEBOX_RUNTIME_DIR", str(runtime))
    os.environ.setdefault("MINEBOX_AUTH_FILE", str(runtime / "auth.json"))
    os.environ.setdefault("MINEBOX_DISPLAY_TOKEN_FILE", str(runtime / "display_token"))
    os.environ.setdefault(
        "MINEBOX_CONFIG", str(ROOT / "config" / "minebox.example.toml")
    )
    os.environ.setdefault(
        "MINEBOX_HARDWARE_CONFIG", str(ROOT / "config" / "hardware.example.toml")
    )

    sys.path.insert(0, str(APP))

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install uvicorn fastapi", file=sys.stderr)
        return 1

    url = "http://127.0.0.1:8080/display/dev"

    def _open() -> None:
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print(f"MineBox display dev UI: {url}")
        print("Fixed layout CSS: 800×480. Resize the window or use device mode.")

    threading.Thread(target=_open, daemon=True).start()
    uvicorn.run("api.server:app", host="127.0.0.1", port=8080, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
