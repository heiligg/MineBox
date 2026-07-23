#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services import backups, scheduler

cfg = scheduler.load()
if not cfg.get("enabled"):
    raise SystemExit(0)
result = backups.create()
if not result.ok:
    print(result.message, file=sys.stderr)
    raise SystemExit(1)
items = backups.list_backups()
for old in items[int(cfg.get("keep_count", 12)):]:
    backups.delete(old)
print(result.stdout or result.message)
