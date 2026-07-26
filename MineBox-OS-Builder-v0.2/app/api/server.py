from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from api.routes import backups
from api.routes import console_command
from api.routes import join
from api.routes import network
from api.routes import update
from api.routes.auth import router as auth_router
from api.routes.console import router as console_router
from api.routes.dashboard import router as dashboard_router
from api.routes.health import router as health_router
from api.routes.minecraft import router as minecraft_router
from api.routes.servers import router as servers_router
from api.routes.setup import router as setup_router
from api.routes.system import router as system_router
from core.security import AuthenticationMiddleware
from services import auth

APP_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_DIR / "web" / "static"

app = FastAPI(
    title="MineBox API",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)

# Register the authentication gate first.
# Starlette applies middleware in reverse registration order.
app.add_middleware(AuthenticationMiddleware)

# Register sessions last so SessionMiddleware is the outer layer and
# request.session exists before AuthenticationMiddleware runs.
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.get_session_secret(),
    session_cookie="minebox_session",
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
    https_only=False,
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(health_router)
app.include_router(system_router)
app.include_router(minecraft_router)
app.include_router(console_router)
app.include_router(setup_router)
app.include_router(servers_router)
app.include_router(console_command.router)
app.include_router(backups.router)
app.include_router(network.router)
app.include_router(update.router)
app.include_router(join.router)


@app.get("/docs-home", include_in_schema=False)
def docs_home():
    return RedirectResponse("/docs")
