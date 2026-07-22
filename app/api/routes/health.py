from fastapi import APIRouter
from typing import Any

router = APIRouter(
    prefix="/api/v1",
    tags=["System"],
)

API_VERSION = "0.1.0"


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "minebox-api",
        "version": API_VERSION,
    }
