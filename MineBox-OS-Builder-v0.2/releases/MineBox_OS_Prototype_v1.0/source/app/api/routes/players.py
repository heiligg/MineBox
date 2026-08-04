from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import players


router = APIRouter(
    prefix="/api/v1/players",
    tags=["Players"],
)


class PlayerActionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=16)
    reason: str = Field(default="", max_length=200)


def _http_error(error: players.PlayersError) -> HTTPException:
    message = str(error)
    lower = message.lower()
    status = 400
    if "start the minecraft server" in lower:
        status = 409
    elif "no active" in lower or "missing" in lower:
        status = 400
    elif "rcon" in lower:
        status = 503
    return HTTPException(status_code=status, detail=message)


@router.get("")
def get_players() -> dict[str, Any]:
    try:
        payload = players.status()
    except players.PlayersError as error:
        raise _http_error(error) from error
    return {"ok": True, **payload}


@router.post("/op")
def post_op(body: PlayerActionRequest) -> dict[str, Any]:
    try:
        return players.op_player(body.name)
    except players.PlayersError as error:
        raise _http_error(error) from error


@router.post("/deop")
def post_deop(body: PlayerActionRequest) -> dict[str, Any]:
    try:
        return players.deop_player(body.name)
    except players.PlayersError as error:
        raise _http_error(error) from error


@router.post("/whitelist/add")
def post_whitelist_add(body: PlayerActionRequest) -> dict[str, Any]:
    try:
        return players.whitelist_add(body.name)
    except players.PlayersError as error:
        raise _http_error(error) from error


@router.post("/whitelist/remove")
def post_whitelist_remove(body: PlayerActionRequest) -> dict[str, Any]:
    try:
        return players.whitelist_remove(body.name)
    except players.PlayersError as error:
        raise _http_error(error) from error


@router.post("/ban")
def post_ban(body: PlayerActionRequest) -> dict[str, Any]:
    try:
        return players.ban_player(body.name, body.reason)
    except players.PlayersError as error:
        raise _http_error(error) from error


@router.post("/pardon")
def post_pardon(body: PlayerActionRequest) -> dict[str, Any]:
    try:
        return players.pardon_player(body.name)
    except players.PlayersError as error:
        raise _http_error(error) from error


@router.post("/kick")
def post_kick(body: PlayerActionRequest) -> dict[str, Any]:
    try:
        return players.kick_player(body.name, body.reason)
    except players.PlayersError as error:
        raise _http_error(error) from error
