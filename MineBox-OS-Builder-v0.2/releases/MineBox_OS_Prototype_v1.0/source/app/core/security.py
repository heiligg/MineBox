"""Authentication, setup gating, and CSRF middleware."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from core.csrf import (
    CSRF_HEADER,
    SAFE_METHODS,
    ensure_csrf_token,
    validate_csrf,
)
from services import auth

try:
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, RedirectResponse, Response

    _FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - desktop CI without FastAPI
    Request = Any  # type: ignore[misc,assignment]
    BaseHTTPMiddleware = object  # type: ignore[misc,assignment]
    JSONResponse = object  # type: ignore[misc,assignment]
    RedirectResponse = object  # type: ignore[misc,assignment]
    Response = object  # type: ignore[misc,assignment]
    _FASTAPI_AVAILABLE = False

# Always public (health / auth entry / static).
PUBLIC_PATHS = {
    "/login",
    "/auth/login",
    "/auth/setup",
    "/api/v1/auth/status",
    "/api/v1/auth/csrf",
    "/health",
    "/api/v1/health",
    "/favicon.ico",
    "/display",
    "/display/dev",
    "/api/v1/display/trust",
    "/api/v1/display/action-map",
    "/api/v1/display/snapshot",
    "/api/v1/display/events",
    "/api/v1/display/session",
}

# Readable while first-boot incomplete (no mutations).
SETUP_PUBLIC_PREFIXES = (
    "/setup",
    "/first-boot",
    "/api/v1/first-boot",
    "/api/v1/status/foundation",
    "/api/v1/status/setup",
    "/api/v1/status/hardware",
    "/api/v1/hardware/diag",
    "/api/v1/providers",
)

# Network read/write needed for SoftAP first-boot Wi-Fi step only while incomplete.
SETUP_NETWORK_PREFIX = "/api/v1/network"

# Minecraft setup APIs while incomplete (create server / versions).
SETUP_MINECRAFT_PREFIX = "/api/v1/setup"

# Destructive / control prefixes blocked until appliance setup complete.
BLOCKED_UNTIL_SETUP_COMPLETE = (
    "/api/v1/minecraft/start",
    "/api/v1/minecraft/stop",
    "/api/v1/minecraft/restart",
    "/api/v1/minecraft/recover",
    "/api/v1/console",
    "/api/v1/files",
    "/api/v1/update",
    "/api/v1/updates",
    "/api/v1/system/shutdown",
    "/api/v1/system/reboot",
    "/api/v1/join",
)


def docs_enabled() -> bool:
    if os.environ.get("MINEBOX_ENABLE_DOCS", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if os.environ.get("MINEBOX_DEV_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return False


def appliance_setup_incomplete() -> bool:
    try:
        from services.first_boot import is_appliance_setup_complete

        return not is_appliance_setup_complete()
    except Exception:
        # Fall back to Minecraft marker for early boot.
        try:
            from api.routes.dashboard import minebox_is_configured

            return not minebox_is_configured() or not auth.is_configured()
        except Exception:
            return True


def _path_blocked_until_complete(path: str, method: str) -> bool:
    if method.upper() in SAFE_METHODS and path.startswith("/api/v1/status"):
        return False
    for prefix in BLOCKED_UNTIL_SETUP_COMPLETE:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    # Restore / delete backups
    if path.startswith("/api/v1/backups/") and method.upper() in {"POST", "DELETE", "PUT"}:
        return True
    if path == "/api/v1/backups" and method.upper() == "POST":
        return True
    return False


def _is_setup_public(path: str, method: str, incomplete: bool) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/static/"):
        return True
    if incomplete:
        if path.startswith(SETUP_PUBLIC_PREFIXES) or path in {"/setup", "/servers"}:
            return True
        if path.startswith(SETUP_MINECRAFT_PREFIX):
            return True
        if path.startswith(SETUP_NETWORK_PREFIX):
            return True
        if path.startswith("/api/v1/status/") or path.startswith("/api/v1/providers"):
            return True
    if docs_enabled() and (
        path.startswith("/docs")
        or path.startswith("/redoc")
        or path in {"/openapi.json", "/api/v1/openapi.json", "/docs-home"}
    ):
        return True
    return False


class AuthenticationMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not _FASTAPI_AVAILABLE:  # pragma: no cover
            raise RuntimeError("FastAPI/Starlette is required to run the API")
        path = request.url.path
        method = request.method.upper()
        incomplete = appliance_setup_incomplete()

        # Issue CSRF token for browser sessions on safe methods.
        if method in SAFE_METHODS:
            try:
                ensure_csrf_token(request.session)
            except Exception:
                pass

        # Local display API uses loopback token trust (not admin CSRF sessions).
        if path.startswith("/api/v1/display/"):
            response = await call_next(request)
            return _with_csrf_header(request, response)

        if _is_setup_public(path, method, incomplete):
            # Login/admin-create are rate-limited and exempt from CSRF.
            # Other setup mutations require CSRF once a session cookie exists.
            if (
                method not in SAFE_METHODS
                and path not in {"/auth/login", "/auth/setup"}
                and path.startswith("/api/")
            ):
                if request.session.get("csrf_token") and not _check_csrf_header(request):
                    return _csrf_failure(path)
            response = await call_next(request)
            return _with_csrf_header(request, response)

        # Block control plane until appliance setup is complete.
        if incomplete and _path_blocked_until_complete(path, method):
            return JSONResponse(
                {
                    "ok": False,
                    "detail": (
                        "MineBox first-boot setup is incomplete. "
                        "Finish the setup wizard before using this control."
                    ),
                    "setup_incomplete": True,
                },
                status_code=403,
            )

        if not auth.is_configured():
            if path.startswith("/api/"):
                return JSONResponse(
                    {
                        "ok": False,
                        "detail": "MineBox authentication setup is required.",
                    },
                    status_code=401,
                )
            return RedirectResponse("/auth/setup", status_code=303)

        if request.session.get("authenticated") is not True:
            if path.startswith("/api/"):
                return JSONResponse(
                    {
                        "ok": False,
                        "detail": "Authentication required.",
                    },
                    status_code=401,
                )
            return RedirectResponse("/login", status_code=303)

        # Authenticated state-changing requests need CSRF (header preferred).
        if method not in SAFE_METHODS and not _check_csrf_header(request):
            return _csrf_failure(path)

        response = await call_next(request)
        return _with_csrf_header(request, response)


def _check_csrf_header(request: Request) -> bool:
    header = request.headers.get(CSRF_HEADER) or request.headers.get("X-CSRF-Token")
    return validate_csrf(request.session, header)


def _csrf_failure(path: str) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "detail": "CSRF validation failed. Refresh the page and try again.",
            "path": path,
        },
        status_code=403,
    )


def _with_csrf_header(request: Request, response: Response) -> Response:
    try:
        token = ensure_csrf_token(request.session)
        response.headers["X-CSRF-Token"] = token
    except Exception:
        pass
    return response
