from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from services import minecraft
from services import monitoring

router = APIRouter()

APP_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(APP_ROOT / "web" / "templates"))


@router.get("/")
def dashboard(request: Request):
    sample = monitoring.sample()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "minecraft": {
                "status": minecraft.status_text(),
                "players": minecraft.player_count_text(),
                "version": minecraft.version(),
                "uptime": minecraft.uptime(),
            },
            "system": {
                "cpu_percent": sample.cpu,
                "memory_percent": sample.memory,
            },
        },
    )
