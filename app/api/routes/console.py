from fastapi import APIRouter, Query

from services import logs

router = APIRouter(
    prefix="/api/v1/console",
    tags=["Console"],
)


@router.get("")
def get_console(
    lines: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {
        "ok": True,
        "console": logs.latest_lines(lines),
    }
