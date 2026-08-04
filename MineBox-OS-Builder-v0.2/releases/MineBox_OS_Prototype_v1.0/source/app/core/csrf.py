"""Session CSRF tokens for cookie-authenticated browser requests."""

from __future__ import annotations

import secrets
from typing import Any

CSRF_SESSION_KEY = "csrf_token"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def ensure_csrf_token(session: Any) -> str:
    token = session.get(CSRF_SESSION_KEY)
    if isinstance(token, str) and len(token) >= 32:
        return token
    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf_token(session: Any) -> str:
    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf(session: Any, provided: str | None) -> bool:
    expected = session.get(CSRF_SESSION_KEY)
    if not isinstance(expected, str) or len(expected) < 32:
        return False
    if not isinstance(provided, str) or not provided:
        return False
    return secrets.compare_digest(expected, provided)
