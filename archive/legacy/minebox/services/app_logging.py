from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from config import APP_LOG, STATE_DIR

_initialized = False

def setup() -> None:
    global _initialized
    if _initialized:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(APP_LOG, maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("minebox")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _initialized = True

def get(name: str) -> logging.Logger:
    setup()
    return logging.getLogger(f"minebox.{name}")
