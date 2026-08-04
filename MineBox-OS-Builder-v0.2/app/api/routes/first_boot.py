"""First-boot wizard and credential rotation APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.csrf import ensure_csrf_token
from core.rate_limit import check_rate_limit, client_key, clear, record_failure
from services import auth, first_boot, secret_rotation
from services.factory_reset import FactoryResetError, factory_reset

router = APIRouter(prefix="/api/v1/first-boot", tags=["First Boot"])


class WizardSaveRequest(BaseModel):
    step: str = Field(min_length=1, max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)


class CredentialsRequest(BaseModel):
    device_name: str | None = Field(default=None, max_length=64)
    hotspot_ssid: str | None = Field(default=None, max_length=32)
    hotspot_psk: str | None = Field(default=None, max_length=63)
    timezone: str | None = Field(default=None, max_length=64)
    os_password: str | None = Field(default=None, max_length=200)
    rotate_rcon: bool = True
    eula_accepted: bool = False


class ReopenRequest(BaseModel):
    confirm: bool = False
    admin_password: str = Field(min_length=1, max_length=200)


class FactoryResetRequest(BaseModel):
    confirm: bool = False
    erase_worlds: bool = False
    confirm_erase_phrase: str = ""
    admin_password: str = ""
    recovery_token: str = ""


@router.get("/status")
def get_status(request: Request) -> dict[str, Any]:
    ensure_csrf_token(request.session)
    return {"ok": True, **first_boot.status()}


@router.put("/wizard")
def save_wizard(body: WizardSaveRequest) -> dict[str, Any]:
    first_boot.save_wizard({"step": body.step, "data": body.data})
    return {"ok": True, **first_boot.status()}


@router.post("/credentials")
def apply_credentials(request: Request, body: CredentialsRequest) -> dict[str, Any]:
    key = client_key(request, "first-boot-credentials")
    allowed, retry = check_rate_limit(key, max_attempts=10, window_s=600, cooldown_s=120)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many setup attempts. Try again in {int(retry)}s.",
        )

    if not body.eula_accepted:
        record_failure(key)
        raise HTTPException(status_code=400, detail="EULA must be accepted.")

    results: dict[str, Any] = {}
    try:
        if body.hotspot_psk:
            results["hotspot"] = secret_rotation.rotate_hotspot_psk(
                body.hotspot_ssid, body.hotspot_psk
            )
        if body.rotate_rcon:
            results["rcon"] = secret_rotation.rotate_rcon_password()
        if body.os_password:
            results["os"] = secret_rotation.rotate_os_password(body.os_password)
        elif not first_boot.load_bootstrap_file().get("os_password_rotated"):
            # Explicit deferred OS step still allowed.
            from core.bootstrap import mark_credential_rotated

            mark_credential_rotated("os_account_password_deferred")
            secret_rotation._mark_os_deferred(True)
            results["os"] = {
                "ok": True,
                "deferred": True,
                "message": "OS password rotation deferred; password SSH will be disabled when possible.",
            }

        # Persist non-secret wizard fields.
        wizard = first_boot.load_wizard()
        data = dict(wizard.get("data") or {})
        if body.device_name:
            data["device_name"] = body.device_name.strip()
        if body.timezone:
            data["timezone"] = body.timezone.strip()
        if body.hotspot_ssid:
            data["hotspot_ssid"] = body.hotspot_ssid.strip()
        first_boot.save_wizard({"step": "credentials_done", "data": data})
        clear(key)
    except secret_rotation.RotationError as exc:
        record_failure(key)
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except Exception as exc:  # noqa: BLE001
        record_failure(key)
        raise HTTPException(status_code=500, detail="Credential rotation failed.") from exc

    return {"ok": True, "results": results, **first_boot.status()}


@router.post("/complete")
def complete_setup(request: Request) -> dict[str, Any]:
    key = client_key(request, "first-boot-complete")
    allowed, retry = check_rate_limit(key, max_attempts=8, window_s=600, cooldown_s=120)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Retry in {int(retry)}s.")
    try:
        status = first_boot.mark_appliance_complete()
        # Best-effort SSH hardening when OS password deferred.
        boot = first_boot.load_bootstrap_file()
        if boot.get("os_password_deferred"):
            status["ssh"] = secret_rotation.disable_password_ssh()
        clear(key)
        return {"ok": True, **status}
    except ValueError as exc:
        record_failure(key)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reopen")
def reopen(body: ReopenRequest) -> dict[str, Any]:
    try:
        return {"ok": True, **first_boot.reopen_setup(
            confirm=body.confirm,
            admin_password=body.admin_password,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/factory-reset")
def reset(request: Request, body: FactoryResetRequest) -> dict[str, Any]:
    key = client_key(request, "factory-reset")
    allowed, retry = check_rate_limit(key, max_attempts=3, window_s=3600, cooldown_s=900)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Too many reset attempts. Retry in {int(retry)}s.")
    try:
        result = factory_reset(
            confirm=body.confirm,
            erase_worlds=body.erase_worlds,
            confirm_erase_phrase=body.confirm_erase_phrase,
            admin_password=body.admin_password,
            recovery_token=body.recovery_token,
        )
        request.session.clear()
        clear(key)
        return result
    except FactoryResetError as exc:
        record_failure(key)
        raise HTTPException(status_code=400, detail=exc.message) from exc
