from fastapi import APIRouter
from typing import Any

from core.version import get_version

router = APIRouter(
    prefix="/api/v1",
    tags=["System"],
)


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "minebox-api",
        "version": get_version(),
    }
