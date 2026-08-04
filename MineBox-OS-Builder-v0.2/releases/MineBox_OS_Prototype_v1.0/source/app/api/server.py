import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from api.routes import backups
from api.routes import console_command
from api.routes import files as files_routes
from api.routes import join
from api.routes import mods as mods_routes
from api.routes import network
from api.routes import players as players_routes
from api.routes import update
from api.routes import appliance as appliance_routes
from api.routes.auth import router as auth_router
from api.routes.console import router as console_router
from api.routes.dashboard import router as dashboard_router
from api.routes.display import router as display_router
from api.routes.first_boot import router as first_boot_router
from api.routes.foundation import router as foundation_router
from api.routes.health import router as health_router
from api.routes.minecraft import router as minecraft_router
from api.routes.remote_access import router as remote_access_router
from api.routes.servers import router as servers_router
from api.routes.setup import router as setup_router
from api.routes.system import router as system_router
from core.security import AuthenticationMiddleware, docs_enabled
from core.version import get_version
from services import auth

APP_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_DIR / "web" / "static"

_DOCS = docs_enabled()
app = FastAPI(
    title="MineBox API",
    version=get_version(),
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/api/v1/openapi.json" if _DOCS else None,
)


@app.on_event("startup")
def _validate_configuration_on_startup() -> None:
    """Fail fast with a readable error if TOML config is invalid."""
    import logging

    logger = logging.getLogger("minebox.config")
    # Do NOT force mock hardware here. Production appliances detect Pi hardware
    # via HAL; CI/dev may set MINEBOX_FORCE_MOCK_HARDWARE=1 or rely on
    # state_service auto-mock when not on a Raspberry Pi.
    try:
        from core.minebox_config import get_config

        cfg = get_config()
        logger.info(
            "MineBox configuration loaded (device=%s profile=%s source=%s)",
            cfg.device_name,
            cfg.hardware_profile,
            cfg.source_path,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("MineBox configuration invalid: %s", exc)
        raise
    try:
        from display.local_trust import ensure_display_token

        ensure_display_token()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Display token provisioning skipped: %s", exc)

# Register the authentication gate first.
# Starlette applies middleware in reverse registration order.
app.add_middleware(AuthenticationMiddleware)

# Register sessions last so SessionMiddleware is the outer layer and
# request.session exists before AuthenticationMiddleware runs.
_https_only = os.environ.get("MINEBOX_SESSION_HTTPS_ONLY", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
try:
    from services import tls

    _https_only = _https_only or bool(tls.status().get("enabled"))
except Exception:
    pass

app.add_middleware(
    SessionMiddleware,
    secret_key=auth.get_session_secret(),
    session_cookie="minebox_session",
    max_age=int(os.environ.get("MINEBOX_SESSION_MAX_AGE", str(60 * 60 * 24 * 14))),
    same_site="lax",
    https_only=_https_only,
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(display_router)
app.include_router(health_router)
app.include_router(foundation_router)
app.include_router(first_boot_router)
app.include_router(system_router)
app.include_router(minecraft_router)
app.include_router(console_router)
app.include_router(setup_router)
app.include_router(servers_router)
app.include_router(console_command.router)
app.include_router(backups.router)
app.include_router(files_routes.router)
app.include_router(players_routes.router)
app.include_router(mods_routes.router)
app.include_router(network.router)
app.include_router(remote_access_router)
app.include_router(update.router)
app.include_router(join.router)
app.include_router(appliance_routes.router)


@app.get("/health", include_in_schema=False)
def root_health():
    """Public liveness alias (also exposed at /api/v1/health)."""
    return {
        "ok": True,
        "service": "minebox-api",
        "version": "0.2.0",
    }


@app.get("/docs-home", include_in_schema=False)
def docs_home():
    if not docs_enabled():
        return RedirectResponse("/", status_code=302)
    return RedirectResponse("/docs")


from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    from fastapi.responses import HTMLResponse, JSONResponse

    if request.url.path.startswith("/api/") or request.url.path.startswith("/auth/"):
        return JSONResponse(
            {"ok": False, "detail": exc.detail},
            status_code=exc.status_code,
        )
    if exc.status_code == 404:
        return HTMLResponse(
            "<!DOCTYPE html><html><head><title>Not found</title></head>"
            "<body style='font-family:Georgia,serif;padding:2rem;background:#1a2332;color:#e8eef7'>"
            "<h1>Page not found</h1>"
            "<p>That page does not exist on this MineBox.</p>"
            "<p><a href='/' style='color:#7db4ff'>Home</a> · "
            "<a href='/login' style='color:#7db4ff'>Login</a></p>"
            "</body></html>",
            status_code=404,
        )
    if exc.status_code in {401, 403}:
        return HTMLResponse(
            "<!DOCTYPE html><html><head><title>Unauthorized</title></head>"
            "<body style='font-family:Georgia,serif;padding:2rem;background:#1a2332;color:#e8eef7'>"
            "<h1>Sign in required</h1>"
            "<p>You need permission to use this page.</p>"
            "<p><a href='/login' style='color:#7db4ff'>Go to login</a></p>"
            "</body></html>",
            status_code=exc.status_code,
        )
    return JSONResponse({"ok": False, "detail": exc.detail}, status_code=exc.status_code)
