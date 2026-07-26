from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from services import auth


PUBLIC_PATHS = {
    "/login",
    "/auth/login",
    "/auth/setup",
    "/api/v1/auth/status",
    "/setup",
    "/servers",
    "/health",
    "/api/v1/health",
    "/favicon.ico",
}


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path

        setup_incomplete = False
        try:
            from api.routes.dashboard import minebox_is_configured

            setup_incomplete = not minebox_is_configured()
        except Exception:
            setup_incomplete = False

        is_public = (
            path in PUBLIC_PATHS
            or path.startswith("/static/")
            or path.startswith("/docs")
            or path.startswith("/redoc")
            or path.startswith("/api/v1/setup")
            or path == "/openapi.json"
            or path == "/api/v1/openapi.json"
            # First-boot Wi-Fi step needs network APIs before a session exists.
            or (setup_incomplete and path.startswith("/api/v1/network"))
        )

        if is_public:
            return await call_next(request)

        if not auth.is_configured():
            if path.startswith("/api/"):
                return JSONResponse(
                    {
                        "ok": False,
                        "detail": (
                            "MineBox authentication setup is required."
                        ),
                    },
                    status_code=401,
                )

            return RedirectResponse(
                "/auth/setup",
                status_code=303,
            )

        if request.session.get("authenticated") is not True:
            if path.startswith("/api/"):
                return JSONResponse(
                    {
                        "ok": False,
                        "detail": "Authentication required.",
                    },
                    status_code=401,
                )

            return RedirectResponse(
                "/login",
                status_code=303,
            )

        return await call_next(request)
