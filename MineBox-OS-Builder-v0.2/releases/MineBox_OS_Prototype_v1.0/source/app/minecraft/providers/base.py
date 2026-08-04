"""Provider interface for MineBox Minecraft server types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class SupportLevel(str, Enum):
    SUPPORTED = "SUPPORTED"
    EXPERIMENTAL = "EXPERIMENTAL"
    UNAVAILABLE = "UNAVAILABLE"
    BROKEN = "BROKEN"


@dataclass(frozen=True)
class JavaRequirement:
    min_major: int
    preferred_major: int
    notes: str = ""


@dataclass
class ProviderValidation:
    ok: bool
    jar_present: bool
    java_ok: bool
    messages: list[str] = field(default_factory=list)
    java_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "jar_present": self.jar_present,
            "java_ok": self.java_ok,
            "messages": list(self.messages),
            "java_version": self.java_version,
        }


@dataclass
class LaunchConfig:
    working_directory: Path
    command: list[str]
    environment: dict[str, str] = field(default_factory=dict)
    main_jar: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "working_directory": str(self.working_directory),
            "command": list(self.command),
            "main_jar": self.main_jar,
            # Never include secrets from environment in public dumps.
            "environment_keys": sorted(self.environment.keys()),
        }


@runtime_checkable
class MinecraftProvider(Protocol):
    name: str
    support_level: SupportLevel

    def java_requirement(self) -> JavaRequirement: ...
    def installation_requirements(self) -> list[str]: ...
    def detect_in_directory(self, server_dir: Path) -> bool: ...
    def validate(self, server_dir: Path, *, java_path: str = "java") -> ProviderValidation: ...
    def version_metadata(self, server_dir: Path) -> dict[str, Any]: ...
    def build_launch_config(
        self,
        server_dir: Path,
        *,
        memory_gb: int,
        java_path: str,
        main_jar: str = "",
    ) -> LaunchConfig: ...
    def supports_update(self) -> bool: ...
    def graceful_stop_commands(self) -> list[str]: ...
    def health_hints(self) -> list[str]: ...
    def to_public_dict(self) -> dict[str, Any]: ...


class BaseProvider:
    name: str = "base"
    support_level: SupportLevel = SupportLevel.UNAVAILABLE

    def java_requirement(self) -> JavaRequirement:
        return JavaRequirement(min_major=17, preferred_major=21)

    def installation_requirements(self) -> list[str]:
        return ["Supported Java runtime", "Writable server directory", "Accepted EULA"]

    def detect_in_directory(self, server_dir: Path) -> bool:
        return False

    def validate(self, server_dir: Path, *, java_path: str = "java") -> ProviderValidation:
        messages: list[str] = []
        jar_present = self.detect_in_directory(server_dir)
        if not jar_present:
            messages.append(f"No {self.name} launch artifacts found in {server_dir}.")
        java_ok, java_version, java_msg = _probe_java(java_path, self.java_requirement())
        if java_msg:
            messages.append(java_msg)
        return ProviderValidation(
            ok=jar_present and java_ok,
            jar_present=jar_present,
            java_ok=java_ok,
            messages=messages,
            java_version=java_version,
        )

    def version_metadata(self, server_dir: Path) -> dict[str, Any]:
        version = ""
        props = server_dir / "server.properties"
        # Prefer MineBox metadata if present later; fall back to version_history / jar name.
        for candidate in ("version.txt", ".minebox-version"):
            path = server_dir / candidate
            if path.is_file():
                try:
                    version = path.read_text(encoding="utf-8").strip().splitlines()[0]
                    break
                except OSError:
                    pass
        return {
            "provider": self.name,
            "support_level": self.support_level.value,
            "version": version or None,
            "directory": str(server_dir),
            "has_properties": props.is_file(),
        }

    def build_launch_config(
        self,
        server_dir: Path,
        *,
        memory_gb: int,
        java_path: str,
        main_jar: str = "",
    ) -> LaunchConfig:
        jar = main_jar or self._default_jar_name(server_dir)
        command = [
            java_path,
            f"-Xms{memory_gb}G",
            f"-Xmx{memory_gb}G",
            "-jar",
            jar,
            "nogui",
        ]
        return LaunchConfig(
            working_directory=server_dir,
            command=command,
            main_jar=jar,
        )

    def _default_jar_name(self, server_dir: Path) -> str:
        return "server.jar"

    def supports_update(self) -> bool:
        return True

    def graceful_stop_commands(self) -> list[str]:
        return ["save-all flush", "stop"]

    def health_hints(self) -> list[str]:
        return ["Done (", "For help, type"]

    def to_public_dict(self) -> dict[str, Any]:
        req = self.java_requirement()
        return {
            "id": self.name,
            "name": self.name,
            "status": self.support_level.value,
            "support_level": self.support_level.value,
            "v1_official": self.support_level is SupportLevel.SUPPORTED,
            "preserved": True,
            "java": {
                "min_major": req.min_major,
                "preferred_major": req.preferred_major,
                "notes": req.notes,
            },
            "installation_requirements": self.installation_requirements(),
            "supports_update": self.supports_update(),
        }


def _probe_java(java_path: str, requirement: JavaRequirement) -> tuple[bool, str | None, str | None]:
    import re
    import subprocess

    try:
        result = subprocess.run(
            [java_path, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, None, f"Java not available ({java_path}): {exc}"

    text = (result.stderr or result.stdout or "").strip()
    match = re.search(r'version\s+"(\d+)(?:\.(\d+))?', text)
    if not match:
        # Missing java binary often returns non-zero with empty useful text.
        if result.returncode != 0 and not text:
            return False, None, f"Java not found or failed: {java_path}"
        return False, None, "Could not parse Java version."
    major = int(match.group(1))
    if major == 1 and match.group(2):
        major = int(match.group(2))
    version = match.group(0).replace("version ", "").strip().strip('"')
    if major < requirement.min_major:
        return (
            False,
            version,
            f"Java {major} is below required major {requirement.min_major} for this provider.",
        )
    return True, version, None
