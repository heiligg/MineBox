from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import APP_VERSION

APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = APP_DIR.parent
REPOSITORY_DIR = Path(os.environ.get("MINEBOX_REPOSITORY_DIR", str(PROJECT_DIR))).expanduser().resolve()
DEV_MODE = os.environ.get("MINEBOX_DEV_MODE", "0") == "1"
RUNTIME_DIR = Path(os.environ.get("MINEBOX_RUNTIME_DIR", str(REPOSITORY_DIR / "runtime") if DEV_MODE else "/var/lib/minebox"))
UPDATE_STATUS_FILE = Path(os.environ.get("MINEBOX_UPDATE_STATUS_FILE", str(RUNTIME_DIR / "updates" / "update-status.json")))
UPDATE_LOG_FILE = Path(os.environ.get("MINEBOX_UPDATE_LOG_FILE", str(RUNTIME_DIR / "updates" / "update.log")))
UPDATE_REMOTE = os.environ.get("MINEBOX_UPDATE_REMOTE", "").strip()
UPDATE_BRANCH = os.environ.get("MINEBOX_UPDATE_BRANCH", "").strip()
UPDATE_CHANNEL = os.environ.get("MINEBOX_UPDATE_CHANNEL", "development" if DEV_MODE else "stable").strip()
DEPLOY_KEY = Path(os.environ.get("MINEBOX_UPDATE_DEPLOY_KEY", "/home/minebox/.ssh/minebox_update"))

class UpdateError(RuntimeError):
    pass

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _run(command: list[str], *, timeout: int = 120, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=process_env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(str(exc)) from exc
    if check and result.returncode != 0:
        raise UpdateError(result.stderr.strip() or result.stdout.strip() or "The update command failed.")
    return result

def _git(*args: str, timeout: int = 120, env: dict[str, str] | None = None) -> str:
    return _run(["git", "-C", str(REPOSITORY_DIR), *args], timeout=timeout, env=env).stdout.strip()

def _git_environment() -> dict[str, str]:
    if DEPLOY_KEY.exists():
        return {"GIT_SSH_COMMAND": f"ssh -i {DEPLOY_KEY} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new"}
    return {}

def repository_exists() -> bool:
    return (REPOSITORY_DIR / ".git").exists()

def _remote_names() -> list[str]:
    if not repository_exists():
        return []
    try:
        return [x for x in _git("remote").splitlines() if x]
    except UpdateError:
        return []

def resolved_remote() -> str | None:
    names = _remote_names()
    for name in (UPDATE_REMOTE, "updates", "origin"):
        if name and name in names:
            return name
    return names[0] if names else None

def _remote_has_branch(remote: str, branch: str) -> bool:
    result = _run(["git", "-C", str(REPOSITORY_DIR), "ls-remote", "--exit-code", "--heads", remote, branch], timeout=120, env=_git_environment(), check=False)
    return result.returncode == 0 and bool(result.stdout.strip())

def resolved_branch() -> str | None:
    remote = resolved_remote()
    if not remote:
        return None
    channel_defaults = {"stable": "main", "beta": "beta", "development": "v0.3-alpha"}
    candidates = [UPDATE_BRANCH, channel_defaults.get(UPDATE_CHANNEL, "")]
    try:
        upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        if upstream.startswith(remote + "/"):
            candidates.append(upstream.split("/", 1)[1])
    except UpdateError:
        pass
    candidates.extend(["main", "master"])
    seen: set[str] = set()
    for branch in candidates:
        branch = branch.strip()
        if branch and branch not in seen:
            seen.add(branch)
            if _remote_has_branch(remote, branch):
                return branch
    return None

def repository_url() -> str | None:
    remote = resolved_remote()
    if not remote:
        return None
    try:
        return _git("remote", "get-url", remote)
    except UpdateError:
        return None

def current_commit() -> str | None:
    try:
        return _git("rev-parse", "HEAD") if repository_exists() else None
    except UpdateError:
        return None

def latest_commit() -> str | None:
    remote, branch = resolved_remote(), resolved_branch()
    if not remote or not branch:
        return None
    try:
        return _git("rev-parse", f"{remote}/{branch}")
    except UpdateError:
        return None

def has_local_changes() -> bool:
    try:
        return bool(_git("status", "--porcelain", "--untracked-files=no")) if repository_exists() else False
    except UpdateError:
        return False

def _read_status() -> dict[str, Any]:
    default = {"state": "unknown", "message": "No updater status is available yet.", "updated_at": None}
    try:
        value = json.loads(UPDATE_STATUS_FILE.read_text(encoding="utf-8"))
        return {**default, **value} if isinstance(value, dict) else default
    except (OSError, json.JSONDecodeError):
        return default

def _short(value: str | None) -> str | None:
    return value[:7] if value else None

def status() -> dict[str, Any]:
    current, latest = current_commit(), latest_commit()
    updater = _read_status()
    running_states = {"starting", "staging", "validating", "switching", "restarting"}
    return {
        "ok": True, "version": APP_VERSION, "channel": UPDATE_CHANNEL,
        "branch": resolved_branch(), "remote": resolved_remote(),
        "current_commit": current, "current_commit_short": _short(current),
        "latest_commit": latest, "latest_commit_short": _short(latest),
        "update_available": bool(current and latest and current != latest),
        "local_changes": has_local_changes(), "local_changes_policy": "preserved_release_swap",
        "repository_available": repository_exists() and repository_url() is not None,
        "repository_dir": str(REPOSITORY_DIR), "updater": updater,
        "service": {"active_state": "activating" if updater.get("state") in running_states else "inactive", "sub_state": updater.get("state"), "result": "success"},
    }

def check_for_updates() -> dict[str, Any]:
    remote, branch = resolved_remote(), resolved_branch()
    if not repository_exists():
        raise UpdateError(f"The MineBox Git repository could not be found at {REPOSITORY_DIR}.")
    if not remote or not branch:
        raise UpdateError("MineBox could not determine an update remote and branch.")
    _git("fetch", "--prune", remote, branch, timeout=300, env=_git_environment())
    result = status()
    result["message"] = "A MineBox update is available." if result["update_available"] else "MineBox is already up to date."
    return result

def install_update() -> dict[str, Any]:
    current = status()
    updater_state = current["updater"].get("state")
    if updater_state in {"starting", "staging", "validating", "switching", "restarting"}:
        return {"ok": True, "started": False, "message": "A MineBox update is already running.", "service": current["service"]}
    url, branch, target = repository_url(), resolved_branch(), latest_commit()
    if not url or not branch or not target:
        raise UpdateError("No valid MineBox update source is configured. Check for updates first.")
    if has_local_changes():
        raise UpdateError("Tracked source files have local changes. Commit them before installing an update; runtime data is preserved automatically.")

    stage = REPOSITORY_DIR.with_name(REPOSITORY_DIR.name + ".update")
    previous = REPOSITORY_DIR.with_name(REPOSITORY_DIR.name + ".previous")
    data_root = REPOSITORY_DIR.with_name(REPOSITORY_DIR.name + ".data")
    helper_source = APP_DIR / "scripts" / "minebox_updater.py"
    if not helper_source.is_file():
        raise UpdateError("The detached updater helper is missing.")

    temp_dir = Path(tempfile.mkdtemp(prefix="minebox-updater-"))
    helper = temp_dir / "minebox_updater.py"
    payload_file = temp_dir / "payload.json"
    shutil.copy2(helper_source, helper)
    payload = {
        "current_dir": str(REPOSITORY_DIR), "stage_dir": str(stage), "previous_dir": str(previous),
        "data_root": str(data_root), "status_file": str(UPDATE_STATUS_FILE), "log_file": str(UPDATE_LOG_FILE),
        "repository_url": url, "branch": branch, "target_commit": target, "old_commit": current_commit(),
        "parent_pid": os.getpid(), "mode": "development" if DEV_MODE else "production",
        "restart_command": os.environ.get("MINEBOX_UPDATE_RESTART_COMMAND", ""),
        "health_url": os.environ.get("MINEBOX_UPDATE_HEALTH_URL", "http://127.0.0.1:8080/api/v1/health"),
        "git_env": _git_environment(),
    }
    payload_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    UPDATE_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPDATE_STATUS_FILE.write_text(json.dumps({"state": "starting", "message": "Starting the detached MineBox updater.", "updated_at": _utc_now(), "old_commit": current_commit(), "new_commit": target}, indent=2) + "\n", encoding="utf-8")
    log_handle = open(UPDATE_LOG_FILE, "a", encoding="utf-8")
    subprocess.Popen([os.environ.get("PYTHON", "python3"), str(helper), str(payload_file)], stdin=subprocess.DEVNULL, stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    log_handle.close()
    return {"ok": True, "started": True, "message": "MineBox is staging the update safely. The dashboard will restart automatically.", "service": {"active_state": "activating", "sub_state": "starting", "result": "success"}}

def read_update_log(lines: int = 100) -> dict[str, Any]:
    safe = max(1, min(lines, 500))
    try:
        content = UPDATE_LOG_FILE.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        content = ""
    except OSError as exc:
        raise UpdateError(f"The update log could not be read: {exc}") from exc
    return {"ok": True, "lines": safe, "log": "\n".join(content.splitlines()[-safe:])}
