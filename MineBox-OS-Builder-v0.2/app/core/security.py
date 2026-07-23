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

        is_public = (
            path in PUBLIC_PATHS
            or path.startswith("/static/")
            or path.startswith("/docs")
            or path.startswith("/redoc")
            or path == "/openapi.json"
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
