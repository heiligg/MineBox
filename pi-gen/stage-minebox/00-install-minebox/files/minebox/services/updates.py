from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import APP_VERSION


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = APP_DIR.parent
REPOSITORY_DIR = Path(
    os.environ.get("MINEBOX_REPOSITORY_DIR", str(PROJECT_DIR))
).expanduser().resolve()
DEV_MODE = os.environ.get("MINEBOX_DEV_MODE", "0") == "1"

# Production images can override these paths. During local development they stay
# inside the repository so the dashboard does not require root permissions.
_runtime_dir = REPOSITORY_DIR / "runtime" / "updates"
UPDATE_STATUS_FILE = Path(
    os.environ.get(
        "MINEBOX_UPDATE_STATUS_FILE",
        str(_runtime_dir / "update-status.json") if DEV_MODE else "/var/lib/minebox/update-status.json",
    )
)
UPDATE_LOG_FILE = Path(
    os.environ.get(
        "MINEBOX_UPDATE_LOG_FILE",
        str(_runtime_dir / "update.log") if DEV_MODE else "/var/log/minebox/update.log",
    )
)

UPDATE_REMOTE = os.environ.get("MINEBOX_UPDATE_REMOTE", "").strip()
UPDATE_BRANCH = os.environ.get("MINEBOX_UPDATE_BRANCH", "").strip()
DEPLOY_KEY = Path(
    os.environ.get("MINEBOX_UPDATE_DEPLOY_KEY", "/home/minebox/.ssh/minebox_update")
)

_UPDATE_LOCK = threading.Lock()
_UPDATE_THREAD: threading.Thread | None = None


class UpdateError(RuntimeError):
    """Raised when the MineBox update system cannot complete an operation."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _append_log(message: str) -> None:
    try:
        _ensure_parent(UPDATE_LOG_FILE)
        with UPDATE_LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"[{_utc_now()}] {message.rstrip()}\n")
    except OSError:
        # Logging must never make an update operation fail.
        pass


def _write_status(state: str, message: str, **extra: Any) -> None:
    payload = {
        "state": state,
        "message": message,
        "updated_at": _utc_now(),
        **extra,
    }
    try:
        _ensure_parent(UPDATE_STATUS_FILE)
        UPDATE_STATUS_FILE.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _run(
    command: list[str],
    *,
    timeout: int = 120,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    process_environment = os.environ.copy()
    if env:
        process_environment.update(env)

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=process_environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpdateError("The update operation timed out.") from exc
    except OSError as exc:
        raise UpdateError(str(exc)) from exc

    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "The update command failed."
        raise UpdateError(detail)

    return result


def _git(*arguments: str, timeout: int = 120, env: dict[str, str] | None = None) -> str:
    return _run(
        ["git", "-C", str(REPOSITORY_DIR), *arguments],
        timeout=timeout,
        env=env,
    ).stdout.strip()


def repository_exists() -> bool:
    return (REPOSITORY_DIR / ".git").exists()


def _remote_names() -> list[str]:
    if not repository_exists():
        return []
    try:
        return [line.strip() for line in _git("remote").splitlines() if line.strip()]
    except UpdateError:
        return []


def resolved_remote() -> str | None:
    names = _remote_names()
    if UPDATE_REMOTE and UPDATE_REMOTE in names:
        return UPDATE_REMOTE
    if "updates" in names:
        return "updates"
    if "origin" in names:
        return "origin"
    return names[0] if names else None


def _remote_has_branch(remote: str, branch: str) -> bool:
    if not remote or not branch:
        return False
    try:
        result = _run(
            [
                "git",
                "-C",
                str(REPOSITORY_DIR),
                "ls-remote",
                "--exit-code",
                "--heads",
                remote,
                branch,
            ],
            timeout=120,
            env=_git_environment(),
            check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except UpdateError:
        return False


def resolved_branch() -> str | None:
    remote = resolved_remote()
    if not remote:
        return None

    # An explicit update branch wins, but only when that branch actually exists
    # on the selected remote. This prevents version labels such as v0.3-alpha
    # from being treated as Git branches when the repository only publishes main.
    if UPDATE_BRANCH and _remote_has_branch(remote, UPDATE_BRANCH):
        return UPDATE_BRANCH

    candidates: list[str] = []

    # Prefer the branch configured as this checkout's upstream.
    try:
        upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        prefix = f"{remote}/"
        if upstream.startswith(prefix):
            candidates.append(upstream[len(prefix):])
    except UpdateError:
        pass

    # Then try the current local branch. It may be a release/version branch that
    # does not exist remotely, so it still must be verified.
    try:
        current = _git("branch", "--show-current")
        if current:
            candidates.append(current)
    except UpdateError:
        pass

    # Ask Git which branch the remote advertises as its default.
    try:
        remote_head = _git("symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD")
        prefix = f"{remote}/"
        if remote_head.startswith(prefix):
            candidates.append(remote_head[len(prefix):])
    except UpdateError:
        pass

    # Common defaults are a final fallback for repositories without a locally
    # cached remote HEAD reference.
    candidates.extend(["main", "master"])

    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if _remote_has_branch(remote, candidate):
            return candidate

    return None


def _git_environment() -> dict[str, str]:
    if DEPLOY_KEY.exists():
        return {
            "GIT_SSH_COMMAND": (
                f"ssh -i {DEPLOY_KEY} -o IdentitiesOnly=yes "
                "-o BatchMode=yes -o StrictHostKeyChecking=accept-new"
            )
        }
    return {}


def current_commit() -> str | None:
    if not repository_exists():
        return None
    try:
        return _git("rev-parse", "HEAD")
    except UpdateError:
        return None


def latest_commit() -> str | None:
    remote = resolved_remote()
    branch = resolved_branch()
    if not remote or not branch:
        return None
    try:
        return _git("rev-parse", f"{remote}/{branch}")
    except UpdateError:
        return None


def has_local_changes() -> bool:
    if not repository_exists():
        return False
    try:
        return bool(_git("status", "--porcelain"))
    except UpdateError:
        return False


def _short_commit(commit: str | None) -> str | None:
    return commit[:7] if commit else None


def read_updater_status() -> dict[str, Any]:
    default_status: dict[str, Any] = {
        "state": "unknown",
        "message": "No updater status is available yet.",
        "old_commit": None,
        "new_commit": None,
        "updated_at": None,
        "saved_changes": None,
    }
    try:
        parsed = json.loads(UPDATE_STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_status
    return {**default_status, **parsed} if isinstance(parsed, dict) else default_status


def updater_service_state() -> dict[str, Any]:
    running = _UPDATE_THREAD is not None and _UPDATE_THREAD.is_alive()
    return {
        "active_state": "activating" if running else "inactive",
        "sub_state": "running" if running else "dead",
        "result": "success",
    }


def status() -> dict[str, Any]:
    installed_commit = current_commit()
    remote_commit = latest_commit()
    updater = read_updater_status()
    remote = resolved_remote()
    branch = resolved_branch()

    return {
        "ok": True,
        "version": APP_VERSION,
        "channel": "development" if DEV_MODE else "stable",
        "branch": branch,
        "remote": remote,
        "current_commit": installed_commit,
        "current_commit_short": _short_commit(installed_commit),
        "latest_commit": remote_commit,
        "latest_commit_short": _short_commit(remote_commit),
        "update_available": bool(installed_commit and remote_commit and installed_commit != remote_commit),
        "local_changes": has_local_changes(),
        "local_changes_policy": "save_and_replace",
        "repository_available": repository_exists() and remote is not None,
        "repository_dir": str(REPOSITORY_DIR),
        "updater": updater,
        "service": updater_service_state(),
    }


def check_for_updates() -> dict[str, Any]:
    if not repository_exists():
        raise UpdateError(f"The MineBox Git repository could not be found at {REPOSITORY_DIR}.")

    remote = resolved_remote()
    branch = resolved_branch()
    if not remote:
        raise UpdateError("No Git remote is configured for MineBox updates.")
    if not branch:
        raise UpdateError("MineBox could not determine which Git branch to update.")

    _append_log(f"Checking {remote}/{branch} for updates.")
    _git("fetch", "--prune", remote, branch, timeout=300, env=_git_environment())
    result = status()
    result["message"] = (
        "A MineBox update is available."
        if result["update_available"]
        else "MineBox is already up to date."
    )
    return result


def _save_local_changes() -> str | None:
    if not has_local_changes():
        return None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    message = f"MineBox automatic update backup {stamp}"
    before = _git("stash", "list", "--format=%gd", timeout=30).splitlines()
    _git("stash", "push", "--include-untracked", "--message", message, timeout=300)
    after = _git("stash", "list", "--format=%gd", timeout=30).splitlines()

    saved_ref = after[0] if after and after != before else "git stash"
    _append_log(f"Saved uncommitted changes in {saved_ref} ({message}).")
    return saved_ref


def _perform_update() -> None:
    old_commit = current_commit()
    saved_changes: str | None = None
    remote = resolved_remote()
    branch = resolved_branch()

    try:
        if not remote or not branch:
            raise UpdateError("The update remote or branch is not configured.")

        _write_status("updating", "Preparing the MineBox update.", old_commit=old_commit)
        _append_log("Starting MineBox update.")

        saved_changes = _save_local_changes()
        if saved_changes:
            _write_status(
                "updating",
                "Local changes were saved safely. Downloading the update.",
                old_commit=old_commit,
                saved_changes=saved_changes,
            )

        _append_log(f"Fetching {remote}/{branch}.")
        _git("fetch", "--prune", remote, branch, timeout=600, env=_git_environment())

        target = f"{remote}/{branch}"
        _append_log(f"Installing {target}.")
        _git("reset", "--hard", target, timeout=120)
        _git("clean", "-fd", "--exclude=runtime/", timeout=120)

        new_commit = current_commit()
        message = "MineBox was updated successfully."
        if saved_changes:
            message += f" Previous uncommitted changes were saved in {saved_changes}."

        _write_status(
            "success",
            message,
            old_commit=old_commit,
            new_commit=new_commit,
            saved_changes=saved_changes,
        )
        _append_log(message)
    except Exception as exc:  # keep background failures visible in the dashboard
        message = str(exc) or exc.__class__.__name__
        _write_status(
            "failed",
            message,
            old_commit=old_commit,
            new_commit=current_commit(),
            saved_changes=saved_changes,
        )
        _append_log(f"Update failed: {message}")
    finally:
        _UPDATE_LOCK.release()


def install_update() -> dict[str, Any]:
    global _UPDATE_THREAD

    if not repository_exists():
        raise UpdateError(f"The MineBox Git repository could not be found at {REPOSITORY_DIR}.")
    if not resolved_remote():
        raise UpdateError("No Git remote is configured for MineBox updates.")

    if not _UPDATE_LOCK.acquire(blocking=False):
        return {
            "ok": True,
            "started": False,
            "message": "A MineBox update is already running.",
            "service": updater_service_state(),
        }

    _UPDATE_THREAD = threading.Thread(
        target=_perform_update,
        name="minebox-updater",
        daemon=True,
    )
    _UPDATE_THREAD.start()

    message = "The MineBox update has started."
    if has_local_changes():
        message += " Uncommitted changes will be saved automatically before installation."

    return {
        "ok": True,
        "started": True,
        "message": message,
        "service": updater_service_state(),
    }


def read_update_log(lines: int = 100) -> dict[str, Any]:
    safe_lines = max(1, min(lines, 500))
    try:
        content = UPDATE_LOG_FILE.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        content = ""
    except OSError as exc:
        raise UpdateError(f"The update log could not be read: {exc}") from exc

    return {
        "ok": True,
        "lines": safe_lines,
        "log": "\n".join(content.splitlines()[-safe_lines:]),
    }
