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
        response = rcon.command(command)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"RCON command failed: {exc}",
        ) from exc

    return {
        "ok": True,
        "command": command,
        "response": response or "Command sent successfully.",
    }
