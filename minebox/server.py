from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from api.routes.health import router as health_router
from api.routes.system import router as system_router
from api.routes.minecraft import router as minecraft_router

app = FastAPI(
    title="MineBox API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


app.include_router(health_router)
app.include_router(system_router)
app.include_router(minecraft_router)