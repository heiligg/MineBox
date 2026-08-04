"""Internal RCON command allowlist / safety (Checkpoint 3)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Exact or prefix-safe commands allowed for internal MineBox automation.
_ALLOWED_EXACT = {
    "list",
    "save-all",
    "save-all flush",
    "save-off",
    "save-on",
    "stop",
    "whitelist list",
    "op list",  # may be unsupported; still "safe" read-ish
}

_ALLOWED_PREFIXES = (
    "whitelist add ",
    "whitelist remove ",
    "op ",
    "deop ",
    "kick ",
    "ban ",
    "pardon ",
    "say ",
    "time set ",
    "gamemode ",
    "difficulty ",
    "weather ",
)

# Never allow shell-like or filesystem destructive patterns via console bridge.
_DENIED_PATTERNS = (
    re.compile(r"[;&|`$]"),
    re.compile(r"\b(rm|del|format|shutdown|reboot)\b", re.I),
)


@dataclass
class CommandSafetyResult:
    allowed: bool
    reason: str
    normalized: str


def normalize_command(command: str) -> str:
    text = (command or "").strip()
    if text.startswith("/"):
        text = text[1:].strip()
    return text


def check_command(command: str) -> CommandSafetyResult:
    normalized = normalize_command(command)
    if not normalized:
        return CommandSafetyResult(False, "Command is empty.", normalized)
    if len(normalized) > 200:
        return CommandSafetyResult(False, "Command is too long.", normalized)
    for pattern in _DENIED_PATTERNS:
        if pattern.search(normalized):
            return CommandSafetyResult(False, "Command contains disallowed characters or tokens.", normalized)
    lower = normalized.lower()
    if lower in _ALLOWED_EXACT:
        return CommandSafetyResult(True, "ok", normalized)
    for prefix in _ALLOWED_PREFIXES:
        if lower.startswith(prefix):
            return CommandSafetyResult(True, "ok", normalized)
    return CommandSafetyResult(
        False,
        "Command is not on the MineBox internal allowlist.",
        normalized,
    )


def assert_safe(command: str) -> str:
    result = check_command(command)
    if not result.allowed:
        raise ValueError(result.reason)
    return result.normalized
