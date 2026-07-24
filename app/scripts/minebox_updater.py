#!/usr/bin/env python3
"""Detached, transactional MineBox updater.

This file is copied to a temporary location before execution so the updater does
not replace the code it is currently running.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now()}] {message.rstrip()}\n")


def status(path: Path, state: str, message: str, **extra: Any) -> None:
    write_json(path, {"state": state, "message": message, "updated_at": now(), **extra})


def run(command: list[str], *, timeout: int = 900, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, env=env)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"Command failed: {' '.join(command)}"
        raise RuntimeError(detail)
    return result


def validate_release(root: Path) -> None:
    required = [
        root / "app" / "api" / "server.py",
        root / "app" / "services" / "updates.py",
        root / "app" / "scripts" / "minebox_updater.py",
        root / "run-dashboard.sh",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Downloaded release is incompatible; missing: " + ", ".join(missing))


def safe_remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def ensure_shared_path(current: Path, stage: Path, data_root: Path, name: str) -> None:
    source = current / name
    shared = data_root / name
    data_root.mkdir(parents=True, exist_ok=True)

    if source.is_symlink():
        target = source.resolve()
        if target != shared.resolve():
            raise RuntimeError(f"{name} points to an unexpected location: {target}")
    elif source.exists():
        if shared.exists():
            raise RuntimeError(f"Cannot preserve {name}: both {source} and {shared} exist.")
        shutil.move(str(source), str(shared))
        source.symlink_to(shared, target_is_directory=True)
    else:
        shared.mkdir(parents=True, exist_ok=True)
        source.symlink_to(shared, target_is_directory=True)

    stage_target = stage / name
    safe_remove(stage_target)
    stage_target.symlink_to(shared, target_is_directory=True)


def wait_for_exit(pid: int, timeout: float = 20.0) -> None:
    if pid <= 1:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.25)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def start_service(root: Path, mode: str, restart_command: str, data_root: Path) -> None:
    if restart_command:
        run(["bash", "-lc", restart_command], timeout=120)
        return
    if mode == "production":
        run(["systemctl", "restart", "minebox-api.service"], timeout=120)
        return

    log_file = data_root / "dashboard.log"
    env = os.environ.copy()
    env["MINEBOX_DEV_MODE"] = "1"
    env["MINEBOX_REPOSITORY_DIR"] = str(root)
    with log_file.open("ab") as handle:
        subprocess.Popen(
            [str(root / "run-dashboard.sh")],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def healthy(url: str, timeout: int = 45) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if 200 <= response.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload")
    args = parser.parse_args()
    cfg = json.loads(Path(args.payload).read_text(encoding="utf-8"))

    current = Path(cfg["current_dir"]).resolve()
    stage = Path(cfg["stage_dir"]).resolve()
    previous = Path(cfg["previous_dir"]).resolve()
    data_root = Path(cfg["data_root"]).resolve()
    status_file = Path(cfg["status_file"]).resolve()
    log_file = Path(cfg["log_file"]).resolve()
    repository_url = cfg["repository_url"]
    branch = cfg["branch"]
    target_commit = cfg.get("target_commit")
    parent_pid = int(cfg.get("parent_pid", 0))
    mode = cfg.get("mode", "development")
    restart_command = cfg.get("restart_command", "")
    health_url = cfg.get("health_url", "http://127.0.0.1:8080/api/v1/health")
    git_env = os.environ.copy()
    git_env.update(cfg.get("git_env", {}))
    git_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    old_commit = cfg.get("old_commit")
    swapped = False

    try:
        status(status_file, "staging", "Preparing the MineBox update.", old_commit=old_commit)
        safe_remove(stage)

        # The API already fetched target_commit before launching this helper.
        # Clone from the local repository instead of GitHub so the detached
        # updater never blocks on credentials or downloads the repository twice.
        log(log_file, f"Staging commit {target_commit or branch} from local repository {current} into {stage}.")
        run(["git", "clone", "--no-hardlinks", "--no-checkout", str(current), str(stage)], timeout=180, env=git_env)
        if target_commit:
            run(["git", "-C", str(stage), "checkout", "--detach", target_commit], timeout=120, env=git_env)
        else:
            run(["git", "-C", str(stage), "checkout", branch], timeout=120, env=git_env)
        new_commit = run(["git", "-C", str(stage), "rev-parse", "HEAD"], env=git_env).stdout.strip()

        status(status_file, "validating", "Validating the prepared release.", old_commit=old_commit, new_commit=new_commit)
        validate_release(stage)
        ensure_shared_path(current, stage, data_root, "runtime")
        if (current / ".venv").exists() or (data_root / ".venv").exists():
            ensure_shared_path(current, stage, data_root, ".venv")

        status(status_file, "switching", "Switching MineBox to the new release.", old_commit=old_commit, new_commit=new_commit)
        log(log_file, "Stopping the running MineBox dashboard.")
        wait_for_exit(parent_pid)

        safe_remove(previous)
        os.replace(current, previous)
        os.replace(stage, current)
        swapped = True

        log(log_file, "Starting the updated MineBox dashboard.")
        start_service(current, mode, restart_command, data_root)
        if not healthy(health_url):
            raise RuntimeError("The updated dashboard failed its health check.")

        status(status_file, "success", "MineBox was updated successfully.", old_commit=old_commit, new_commit=new_commit, rollback_available=True)
        log(log_file, f"Update completed successfully: {old_commit} -> {new_commit}.")
        return 0
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        log(log_file, f"Update failed: {message}")
        if swapped:
            try:
                log(log_file, "Rolling back to the previous MineBox release.")
                failed = current.with_name(current.name + ".failed")
                safe_remove(failed)
                os.replace(current, failed)
                os.replace(previous, current)
                start_service(current, mode, restart_command, data_root)
                rollback_ok = healthy(health_url)
                status(status_file, "rolled_back" if rollback_ok else "failed", f"Update failed and MineBox was {'restored' if rollback_ok else 'not restored'}: {message}", old_commit=old_commit, rollback_succeeded=rollback_ok)
            except Exception as rollback_exc:
                status(status_file, "failed", f"Update failed: {message}. Rollback also failed: {rollback_exc}", old_commit=old_commit, rollback_succeeded=False)
        else:
            status(status_file, "failed", message, old_commit=old_commit, rollback_succeeded=None)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
