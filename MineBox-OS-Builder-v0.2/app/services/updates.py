from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import APP_VERSION


DEFAULT_REPO = "https://github.com/heiligg/MineBox.git"
DEFAULT_BRANCH = "main"
DEFAULT_APP_SUBDIR = "MineBox-OS-Builder-v0.2/app"
CONFIG_FILE = Path("/etc/minebox/updates.conf")

APP_DIR = Path(__file__).resolve().parents[1]
BUILDER_DIR = APP_DIR.parent


class UpdateError(RuntimeError):
    """Raised when the MineBox update system cannot complete an operation."""


def _dev_mode() -> bool:
    return os.environ.get("MINEBOX_DEV_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_config_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if not CONFIG_FILE.is_file():
        return values
    try:
        for raw in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    except OSError:
        return values
    return values


def _config_value(*keys: str, default: str = "") -> str:
    file_values = _load_config_file()
    for key in keys:
        env_key = f"MINEBOX_{key.upper()}"
        if os.environ.get(env_key, "").strip():
            return os.environ[env_key].strip()
        # Also accept MINEBOX_UPDATE_* style already in env names.
        if os.environ.get(key, "").strip():
            return os.environ[key].strip()
        if key in file_values and file_values[key]:
            return file_values[key]
        # updates.conf uses short keys: repo, branch, app_subdir
        short = key.lower().removeprefix("update_")
        if short in file_values and file_values[short]:
            return file_values[short]
    return default


def repository_url() -> str:
    return _config_value(
        "UPDATE_REPO",
        "repo",
        default=DEFAULT_REPO,
    )


def update_branch() -> str:
    return _config_value(
        "UPDATE_BRANCH",
        "branch",
        default=DEFAULT_BRANCH,
    )


def app_subdir() -> str:
    return _config_value(
        "UPDATE_APP_SUBDIR",
        "app_subdir",
        default=DEFAULT_APP_SUBDIR,
    )


def _paths() -> tuple[Path, Path, Path]:
    if _dev_mode():
        root = Path(
            os.environ.get(
                "MINEBOX_REPOSITORY_DIR",
                str(BUILDER_DIR),
            )
        ).expanduser().resolve()
        runtime = root / "runtime" / "updates"
        return (
            runtime / "update-status.json",
            runtime / "update.log",
            runtime / "installed-commit",
        )
    return (
        Path("/var/lib/minebox/update-status.json"),
        Path("/var/log/minebox/update.log"),
        Path("/var/lib/minebox/installed-commit"),
    )


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _append_log(message: str) -> None:
    _, log_file, _ = _paths()
    try:
        _ensure_parent(log_file)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"[{_utc_now()}] {message.rstrip()}\n")
    except OSError:
        pass


def _write_status(state: str, message: str, **extra: Any) -> None:
    status_file, _, _ = _paths()
    payload = {
        "state": state,
        "message": message,
        "updated_at": _utc_now(),
        **extra,
    }
    try:
        _ensure_parent(status_file)
        temporary = status_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(status_file)
    except OSError:
        pass


def read_updater_status() -> dict[str, Any]:
    status_file, _, _ = _paths()
    default = {
        "state": "unknown",
        "message": "No updater status is available yet.",
        "old_commit": None,
        "new_commit": None,
        "updated_at": None,
    }
    try:
        parsed = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(parsed, dict):
        return default
    return {**default, **parsed}


def installed_commit() -> str | None:
    _, _, commit_file = _paths()
    try:
        value = commit_file.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if value:
        return value
    updater = read_updater_status()
    new_commit = updater.get("new_commit")
    if isinstance(new_commit, str) and new_commit.strip():
        return new_commit.strip()
    return None


def _short_commit(commit: str | None) -> str | None:
    if not commit:
        return None
    return commit[:7]


def _run(
    command: list[str],
    *,
    timeout: int = 60,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=process_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpdateError("The update operation timed out.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (
            exc.stderr.strip()
            or exc.stdout.strip()
            or "The update command failed."
        )
        raise UpdateError(detail) from exc
    except OSError as exc:
        raise UpdateError(str(exc)) from exc


def _deploy_key_path() -> Path:
    return Path(
        os.environ.get(
            "MINEBOX_UPDATE_DEPLOY_KEY",
            "/home/minebox/.ssh/minebox_update",
        )
    )


def _git_environment() -> dict[str, str]:
    env: dict[str, str] = {}
    deploy_key = _deploy_key_path()
    if deploy_key.is_file():
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {deploy_key} "
            "-o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=accept-new "
            "-o BatchMode=yes"
        )
    return env


def _effective_repository_url(url: str | None = None) -> str:
    """Use SSH when a deploy key exists so private HTTPS remotes can authenticate.

    Default config uses https://github.com/... but GIT_SSH_COMMAND only applies to
    SSH remotes. Rewrite GitHub HTTPS → SSH when /home/minebox/.ssh/minebox_update
    is present.
    """
    raw = (url or repository_url()).strip()
    if not raw:
        return raw
    deploy_key = _deploy_key_path()
    if not deploy_key.is_file():
        return raw
    prefixes = (
        "https://github.com/",
        "http://github.com/",
        "https://www.github.com/",
    )
    for prefix in prefixes:
        if raw.lower().startswith(prefix):
            path = raw[len(prefix) :].removesuffix(".git").strip("/")
            if path:
                return f"git@github.com:{path}.git"
            break
    return raw


def remote_commit() -> str | None:
    url = _effective_repository_url()
    branch = update_branch()
    if not url or not branch:
        return None
    try:
        result = _run(
            [
                "git",
                "ls-remote",
                url,
                f"refs/heads/{branch}",
            ],
            timeout=60,
            env=_git_environment(),
        )
    except UpdateError as exc:
        _append_log(f"remote_commit failed for {url}: {exc}")
        return None

    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].endswith(f"/{branch}"):
            return parts[0]
        if len(parts) >= 1 and parts[0]:
            return parts[0]
    return None


def updater_service_state() -> dict[str, Any]:
    if _dev_mode():
        updater = read_updater_status()
        state = str(updater.get("state") or "unknown")
        active = "activating" if state in {"updating", "staging", "validating", "switching"} else "inactive"
        return {
            "active_state": active,
            "sub_state": state,
            "result": state,
        }

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
        "active_state": values.get("ActiveState", "unknown"),
        "sub_state": values.get("SubState", "unknown"),
        "result": values.get("Result", "unknown"),
    }


def status() -> dict[str, Any]:
    current = installed_commit()
    latest = remote_commit()
    updater = read_updater_status()
    service = updater_service_state()
    update_available = bool(
        latest
        and (
            current is None
            or current != latest
        )
    )

    return {
        "ok": True,
        "version": APP_VERSION,
        "channel": "development" if _dev_mode() else "stable",
        "branch": update_branch(),
        "repository_url": repository_url(),
        "app_subdir": app_subdir(),
        "current_commit": current,
        "current_commit_short": _short_commit(current),
        "latest_commit": latest,
        "latest_commit_short": _short_commit(latest),
        "update_available": update_available,
        # Appliance installs are not git worktrees; never block the Install button.
        "local_changes": False,
        "repository_available": bool(latest) or bool(repository_url()),
        "updater": updater,
        "service": service,
    }


def check_for_updates() -> dict[str, Any]:
    url = repository_url()
    effective = _effective_repository_url(url)
    branch = update_branch()
    if not url:
        raise UpdateError("No GitHub repository URL is configured for updates.")
    if not branch:
        raise UpdateError("No update branch is configured.")

    _append_log(f"Checking {effective} ({branch}) for updates.")
    latest = remote_commit()
    if not latest:
        deploy = _deploy_key_path()
        if not deploy.is_file():
            raise UpdateError(
                "Latest commit unavailable: the MineBox GitHub repo is private and "
                f"no deploy key was found at {deploy}. "
                "On the Pi: create an SSH key, add it as a GitHub deploy key "
                "(repo Settings → Deploy keys, read-only), then check again."
            )
        raise UpdateError(
            "Latest commit unavailable: git could not read the private repository. "
            f"Tried {effective} with deploy key {deploy}. "
            "Confirm that key is added under GitHub → Settings → Deploy keys."
        )

    result = status()
    result["latest_commit"] = latest
    result["latest_commit_short"] = _short_commit(latest)
    result["update_available"] = bool(
        result["current_commit"] is None
        or result["current_commit"] != latest
    )
    result["repository_available"] = True
    result["repository_url_effective"] = effective
    result["message"] = (
        "A MineBox update is available."
        if result["update_available"]
        else "MineBox is already up to date."
    )
    _append_log(result["message"])
    return result


def _dev_install_worker(target_commit: str | None) -> None:
    apply_script = APP_DIR / "scripts" / "minebox_update_apply.py"
    status_file, log_file, commit_file = _paths()
    env = os.environ.copy()
    env["MINEBOX_DEV_MODE"] = "1"
    env["MINEBOX_UPDATE_REPO"] = repository_url()
    env["MINEBOX_UPDATE_BRANCH"] = update_branch()
    env["MINEBOX_UPDATE_APP_SUBDIR"] = app_subdir()
    env["MINEBOX_UPDATE_STATUS_FILE"] = str(status_file)
    env["MINEBOX_UPDATE_LOG_FILE"] = str(log_file)
    env["MINEBOX_UPDATE_COMMIT_FILE"] = str(commit_file)
    env["MINEBOX_UPDATE_TARGET"] = str(APP_DIR)
    env["MINEBOX_REPOSITORY_DIR"] = str(BUILDER_DIR)
    if target_commit:
        env["MINEBOX_UPDATE_TARGET_COMMIT"] = target_commit

    _write_status(
        "updating",
        "Starting the MineBox development update.",
        old_commit=installed_commit(),
    )
    _append_log("Starting development update apply script.")
    try:
        subprocess.run(
            [sys.executable, str(apply_script), "--dev"],
            check=True,
            timeout=900,
            env=env,
        )
    except Exception as exc:  # noqa: BLE001 - surface any apply failure in status
        message = str(exc) or exc.__class__.__name__
        _write_status(
            "failed",
            message,
            old_commit=installed_commit(),
        )
        _append_log(f"Development update failed: {message}")


def install_update() -> dict[str, Any]:
    service_state = updater_service_state()
    if service_state["active_state"] == "activating":
        return {
            "ok": True,
            "started": False,
            "message": "A MineBox update is already running.",
            "service": service_state,
        }

    latest = remote_commit()
    if not latest:
        raise UpdateError(
            "Could not determine the latest GitHub commit to install."
        )

    if _dev_mode():
        thread = threading.Thread(
            target=_dev_install_worker,
            args=(latest,),
            name="minebox-dev-updater",
            daemon=True,
        )
        thread.start()
        return {
            "ok": True,
            "started": True,
            "message": "The MineBox update has started.",
            "service": updater_service_state(),
        }

    result = subprocess.run(
        [
            "sudo",
            "-n",
            "/usr/bin/systemctl",
            "start",
            "minebox-update.service",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or "The update service could not be started."
        )
        raise UpdateError(detail)

    _write_status(
        "updating",
        "The MineBox update service has been started.",
        old_commit=installed_commit(),
        target_commit=latest,
    )
    _append_log("Started minebox-update.service.")
    return {
        "ok": True,
        "started": True,
        "message": "The MineBox update has started.",
        "service": updater_service_state(),
    }


def read_update_log(lines: int = 100) -> dict[str, Any]:
    _, log_file, _ = _paths()
    safe_lines = max(1, min(lines, 500))
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        content = ""
    except OSError as exc:
        raise UpdateError(f"The update log could not be read: {exc}") from exc

    return {
        "ok": True,
        "lines": safe_lines,
        "log": "\n".join(content.splitlines()[-safe_lines:]),
    }
