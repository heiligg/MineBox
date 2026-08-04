from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import minecraft, rcon


router = APIRouter(
    prefix="/api/v1/console",
    tags=["console"],
)


class ConsoleCommandRequest(BaseModel):
    command: str = Field(
        min_length=1,
        max_length=500,
    )


@router.post("/command")
def send_console_command(request: ConsoleCommandRequest):
    command = request.command.strip()

    if command.startswith("/"):
        command = command[1:].strip()

    if not command:
        raise HTTPException(
            status_code=400,
            detail="Enter a Minecraft command.",
        )

    if not minecraft.is_running():
        raise HTTPException(
            status_code=409,
            detail="The Minecraft server is offline.",
        )

    try:
        from services.rcon_safety import assert_safe
        from core.rate_limit import check_rate_limit

        allowed, retry = check_rate_limit(
            "console-command", max_attempts=30, window_s=60, cooldown_s=30
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Console rate limit exceeded. Retry in {int(retry)}s.",
            )
        safe_command = assert_safe(command)
        response = rcon.command(safe_command)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"RCON command failed: {exc}",
        ) from exc

    return {
        "ok": True,
        "command": safe_command,
        "response": response or "Command sent successfully.",
    }
