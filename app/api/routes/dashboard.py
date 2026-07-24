from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from services import minecraft
from services import monitoring
from services import servers


APP_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = APP_DIR / "web" / "templates"

MINECRAFT_DIR = Path("/opt/minecraft")
SERVER_JAR = MINECRAFT_DIR / "server.jar"
SERVER_PROPERTIES = MINECRAFT_DIR / "server.properties"
SETUP_MARKER = servers.METADATA_DIR / ".minebox-setup-complete"

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATE_DIR)


def minebox_is_configured() -> bool:
    if SETUP_MARKER.is_file() or bool(servers.list_servers()):
        return True

    return SERVER_JAR.is_file() and SERVER_PROPERTIES.is_file()


@router.get("/setup", include_in_schema=False)
def setup_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={},
    )


@router.get("/servers", include_in_schema=False)
def servers_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="servers.html",
        context={},
    )


@router.get("/", include_in_schema=False)
def dashboard(request: Request):
    if not minebox_is_configured():
        return RedirectResponse(url="/setup", status_code=307)

    sample = monitoring.sample()
    active = servers.active_server()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "minecraft": {
                "running": minecraft.is_running(),
                "status": minecraft.status_text(),
                "players": minecraft.player_count_text(),
                "version": active.version if active else minecraft.version(),
                "uptime": minecraft.uptime(),
                "logs": minecraft.recent_logs(30),
                "server_name": active.name if active else "Minecraft Server",
                "server_id": active.server_id if active else None,
                "port": active.port if active else 25565,
            },
            "system": {
                "cpu_percent": sample.cpu,
                "memory_percent": sample.memory,
            },
        },
    )
