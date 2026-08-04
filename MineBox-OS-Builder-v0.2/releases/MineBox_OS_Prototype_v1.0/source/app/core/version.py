"""Authoritative MineBox product version loader."""

from __future__ import annotations

from pathlib import Path

# Fallback only if VERSION files are missing from a broken install.
DEFAULT_VERSION = "1.0.0-prototype.1"
PRODUCT_NAME = "MineBox OS Prototype"
RELEASE_NAME = "MineBox OS Prototype v1.0"


def get_version() -> str:
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "VERSION",  # /opt/minebox/VERSION or app/VERSION
        here.parents[1] / "VERSION",  # repo root when running from checkout
        Path("/etc/minebox/VERSION"),
        Path("/opt/minebox/VERSION"),
    ]
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text.splitlines()[0].strip()
        except OSError:
            continue
    return DEFAULT_VERSION


def get_product_meta() -> dict[str, str]:
    return {
        "product_name": PRODUCT_NAME,
        "release_name": RELEASE_NAME,
        "version": get_version(),
        "release_type": "prototype",
    }
