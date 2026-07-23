from html import escape
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
        return RedirectResponse(
            url="/setup",
            status_code=307,
        )

    sample = monitoring.sample()
    active = servers.active_server()
    active_name = active.name if active else "Minecraft Server"
    active_version = active.version if active else minecraft.version()
    active_port = active.port if active else 25565

    context = {
        "request": request,
        "minecraft": {
            "running": minecraft.is_running(),
            "status": minecraft.status_text(),
            "players": minecraft.player_count_text(),
            "version": active_version,
            "uptime": minecraft.uptime(),
            "logs": minecraft.recent_logs(30),
            "server_name": active_name,
            "server_id": active.server_id if active else None,
            "port": active_port,
        },
        "system": {
            "cpu_percent": sample.cpu,
            "memory_percent": sample.memory,
        },
    }

    # Render the existing dashboard and add active-server UI without duplicating
    # the large dashboard template. These replacements can be removed once the
    # dashboard template is split into smaller reusable components.
    template = templates.get_template("index.html")
    page = template.render(context)

    servers_link = """
                <a class="nav-item" href="/servers">
                    <span class="nav-icon">▣</span>
                    <span class="nav-text">Servers</span>
                </a>
"""
    dashboard_link = """                <a class="nav-item active" href="/">
                    <span class="nav-icon">⌂</span>
                    <span class="nav-text">Dashboard</span>
                </a>
"""
    if 'href="/servers"' not in page:
        page = page.replace(dashboard_link, dashboard_link + servers_link, 1)

    page = page.replace(
        '<div class="status-label">Minecraft server</div>',
        (
            '<div class="status-label">Active server</div>'
            f'<div style="margin: -8px 0 16px; font-size: 18px; font-weight: 850;">'
            f'{escape(active_name)}</div>'
        ),
        1,
    )

    page = page.replace(
        """                        <strong class="quick-stat-value">
                            25565
                        </strong>""",
        f"""                        <strong class="quick-stat-value" id="server-port-value">
                            {active_port}
                        </strong>""",
        1,
    )

    page = page.replace(
        "Monitor and control your Minecraft appliance.",
        f"Monitor and control {escape(active_name)}.",
        1,
    )

    return HTMLResponse(page)
