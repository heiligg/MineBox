from __future__ import annotations
import subprocess
from dataclasses import dataclass

@dataclass
class CommandResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

    @property
    def message(self) -> str:
        return (self.stderr or self.stdout or "Command failed without an error message.").strip()

def run(command: list[str], timeout: int = 30) -> CommandResult:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return CommandResult(result.returncode == 0, result.stdout.strip(), result.stderr.strip(), result.returncode)
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(False, stderr=str(exc), returncode=1)

def poweroff() -> CommandResult:
    return run(["sudo", "-n", "/usr/bin/systemctl", "poweroff"])

def reboot() -> CommandResult:
    return run(["sudo", "-n", "/usr/bin/systemctl", "reboot"])

def hostname() -> str:
    result = run(["hostname"])
    return result.stdout if result.ok else "Unknown"
