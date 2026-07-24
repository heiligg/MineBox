from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routes.auth import router as auth_router
from api.routes.backups import router as backups_router
from api.routes.console import router as console_router
from api.routes.console_command import router as console_command_router
from api.routes.dashboard import router as dashboard_router
from api.routes.health import router as health_router
from api.routes.minecraft import router as minecraft_router
from api.routes.network import router as network_router
from api.routes.servers import router as servers_router
from api.routes.setup import router as setup_router
from api.routes.system import router as system_router
from api.routes.update import router as update_router

APP_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = APP_DIR / "web" / "static"

app = FastAPI(
    title="MineBox API",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Page routes and authentication.
app.include_router(auth_router)
app.include_router(dashboard_router)

# MineBox API routes used by the dashboard, setup flow, and server manager.
app.include_router(health_router)
app.include_router(system_router)
app.include_router(minecraft_router)
app.include_router(console_router)
app.include_router(console_command_router)
app.include_router(backups_router)
app.include_router(network_router)
app.include_router(servers_router)
app.include_router(setup_router)
app.include_router(update_router)


@app.get("/docs-home", include_in_schema=False)
def docs_home():
    return RedirectResponse("/docs")
