from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from services import minecraft
from services import monitoring


APP_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = APP_DIR / "web" / "templates"

MINECRAFT_DIR = Path("/opt/minecraft")
SERVER_JAR = MINECRAFT_DIR / "server.jar"
SERVER_PROPERTIES = MINECRAFT_DIR / "server.properties"
SETUP_MARKER = MINECRAFT_DIR / ".minebox-setup-complete"

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATE_DIR)


def minebox_is_configured() -> bool:
    if SETUP_MARKER.is_file():
        return True

    return SERVER_JAR.is_file() and SERVER_PROPERTIES.is_file()


@router.get("/setup", include_in_schema=False)
def setup_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={},
    )


@router.get("/", include_in_schema=False)
def dashboard(request: Request):
    if not minebox_is_configured():
        return RedirectResponse(
            url="/setup",
            status_code=307,
        )

    sample = monitoring.sample()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "minecraft": {
                "running": minecraft.is_running(),
                "status": minecraft.status_text(),
                "players": minecraft.player_count_text(),
                "version": minecraft.version(),
                "uptime": minecraft.uptime(),
                "logs": minecraft.recent_logs(30),
            },
            "system": {
                "cpu_percent": sample.cpu,
                "memory_percent": sample.memory,
            },
        },
    )
