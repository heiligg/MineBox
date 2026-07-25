from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routes.dashboard import router as dashboard_router
from api.routes.health import router as health_router
from api.routes.system import router as system_router
from api.routes.minecraft import router as minecraft_router

APP_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = APP_ROOT / "web"

app = FastAPI(
    title="MineBox API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.mount("/static", StaticFiles(directory=str(WEB_ROOT / "static")), name="static")

app.include_router(dashboard_router)
app.include_router(health_router)
app.include_router(system_router)
app.include_router(minecraft_router)


@app.get("/docs-home", include_in_schema=False)
def docs_home():
    return RedirectResponse("/docs")
