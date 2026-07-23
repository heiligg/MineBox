from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from config import APP_VERSION


REPOSITORY_DIR = Path("/home/minebox/MineBox-OS-Builder-v0.2")
UPDATE_STATUS_FILE = Path("/var/lib/minebox/update-status.json")
UPDATE_LOG_FILE = Path("/var/log/minebox/update.log")

UPDATE_REMOTE = "updates"
UPDATE_BRANCH = "feature/minebox-api"

DEPLOY_KEY = Path("/home/minebox/.ssh/minebox_update")

GIT_SSH_COMMAND = (
    f"ssh -i {DEPLOY_KEY} "
    "-o IdentitiesOnly=yes "
    "-o BatchMode=yes"
)


class UpdateError(RuntimeError):
    """Raised when the MineBox update system cannot complete an operation."""


def _run(
    command: list[str],
    *,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_environment = os.environ.copy()

    if env:
        process_environment.update(env)

    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=process_environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpdateError(
            "The update operation timed out."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (
            exc.stderr.strip()
            or exc.stdout.strip()
            or "The update command failed."
        )

        raise UpdateError(detail) from exc
    except OSError as exc:
        raise UpdateError(str(exc)) from exc


def _git(*arguments: str, timeout: int = 30) -> str:
    result = _run(
        [
            "git",
            "-C",
            str(REPOSITORY_DIR),
            *arguments,
        ],
        timeout=timeout,
    )

    return result.stdout.strip()


def _short_commit(commit: str | None) -> str | None:
    if not commit:
        return None

    return commit[:7]


def repository_exists() -> bool:
    return (REPOSITORY_DIR / ".git").is_dir()


def current_commit() -> str | None:
    if not repository_exists():
        return None

    try:
        return _git("rev-parse", "HEAD")
    except UpdateError:
        return None


def latest_commit() -> str | None:
    if not repository_exists():
        return None

    try:
        return _git(
            "rev-parse",
            f"{UPDATE_REMOTE}/{UPDATE_BRANCH}",
        )
    except UpdateError:
        return None


def has_local_changes() -> bool:
    if not repository_exists():
        return False

    try:
        return bool(_git("status", "--porcelain"))
    except UpdateError:
        return False


def read_updater_status() -> dict[str, Any]:
    default_status: dict[str, Any] = {
        "state": "unknown",
        "message": "No updater status is available yet.",
        "old_commit": None,
        "new_commit": None,
        "updated_at": None,
    }

    try:
        raw_status = UPDATE_STATUS_FILE.read_text(
            encoding="utf-8"
        )
        parsed = json.loads(raw_status)
    except (OSError, json.JSONDecodeError):
        return default_status

    if not isinstance(parsed, dict):
        return default_status

    return {
        **default_status,
        **parsed,
    }


def status() -> dict[str, Any]:
    installed_commit = current_commit()
    remote_commit = latest_commit()
    updater = read_updater_status()

    update_available = bool(
        installed_commit
        and remote_commit
        and installed_commit != remote_commit
    )

    return {
        "ok": True,
        "version": APP_VERSION,
        "channel": "development",
        "branch": UPDATE_BRANCH,
        "current_commit": installed_commit,
        "current_commit_short": _short_commit(
            installed_commit
        ),
        "latest_commit": remote_commit,
        "latest_commit_short": _short_commit(
            remote_commit
        ),
        "update_available": update_available,
        "local_changes": has_local_changes(),
        "repository_available": repository_exists(),
        "updater": updater,
    }


def check_for_updates() -> dict[str, Any]:
    if not repository_exists():
        raise UpdateError(
            "The MineBox Git repository could not be found."
        )

    if not DEPLOY_KEY.exists():
        raise UpdateError(
            "The MineBox updater deploy key could not be found."
        )

    _run(
        [
            "git",
            "-C",
            str(REPOSITORY_DIR),
            "fetch",
            "--quiet",
            UPDATE_REMOTE,
            UPDATE_BRANCH,
        ],
        timeout=60,
        env={
            "GIT_SSH_COMMAND": GIT_SSH_COMMAND,
        },
    )

    result = status()

    if result["update_available"]:
        message = "A MineBox update is available."
    else:
        message = "MineBox is already up to date."

    return {
        **result,
        "message": message,
    }


def updater_service_state() -> dict[str, Any]:
    result = subprocess.run(
        [
            "systemctl",
            "show",
            "minebox-update.service",
            "--property=ActiveState",
            "--property=SubState",
            "--property=Result",
            "--no-pager",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    values: dict[str, str] = {}

    for line in result.stdout.splitlines():
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key] = value

    return {
        "active_state": values.get(
            "ActiveState",
            "unknown",
        ),
        "sub_state": values.get(
            "SubState",
            "unknown",
        ),
        "result": values.get(
            "Result",
            "unknown",
        ),
    }


def install_update() -> dict[str, Any]:
    if has_local_changes():
        raise UpdateError(
            "MineBox contains uncommitted changes. "
            "Commit or remove them before updating."
        )

    service_state = updater_service_state()

    if service_state["active_state"] == "activating":
        return {
            "ok": True,
            "started": False,
            "message": "A MineBox update is already running.",
            "service": service_state,
        }

    result = subprocess.run(
        [
            "sudo",
            "-n",
            "/usr/bin/systemctl",
            "start",
            "--no-block",
            "minebox-update.service",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or "The update service could not be started."
        )

        raise UpdateError(detail)

    return {
        "ok": True,
        "started": True,
        "message": "The MineBox update has started.",
        "service": updater_service_state(),
    }


def read_update_log(lines: int = 100) -> dict[str, Any]:
    safe_lines = max(1, min(lines, 500))

    try:
        content = UPDATE_LOG_FILE.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        content = ""
    except OSError as exc:
        raise UpdateError(
            f"The update log could not be read: {exc}"
        ) from exc

    selected_lines = content.splitlines()[-safe_lines:]

    return {
        "ok": True,
        "lines": safe_lines,
        "log": "\n".join(selected_lines),
    }
