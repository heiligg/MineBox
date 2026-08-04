from __future__ import annotations

from pathlib import Path

from minecraft.providers.base import BaseProvider, JavaRequirement, SupportLevel


class FabricProvider(BaseProvider):
    """Preserved Fabric support — experimental until integration tests pass."""

    name = "fabric"
    support_level = SupportLevel.EXPERIMENTAL

    def java_requirement(self) -> JavaRequirement:
        return JavaRequirement(
            min_major=17,
            preferred_major=21,
            notes="Modern Fabric typically needs Java 17+.",
        )

    def detect_in_directory(self, server_dir: Path) -> bool:
        if (server_dir / "fabric-server-launch.jar").is_file():
            return True
        return (server_dir / "fabric-server-launcher.properties").is_file()

    def _default_jar_name(self, server_dir: Path) -> str:
        if (server_dir / "fabric-server-launch.jar").is_file():
            return "fabric-server-launch.jar"
        return "server.jar"

    def installation_requirements(self) -> list[str]:
        return [
            "Fabric server launch jar",
            "Java 17+",
            "Accepted EULA",
            "Experimental on MineBox Prototype v1",
        ]
