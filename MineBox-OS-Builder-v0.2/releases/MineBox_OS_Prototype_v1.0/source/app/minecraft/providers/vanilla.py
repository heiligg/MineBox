from __future__ import annotations

from pathlib import Path

from minecraft.providers.base import BaseProvider, JavaRequirement, SupportLevel


class VanillaProvider(BaseProvider):
    name = "vanilla"
    support_level = SupportLevel.SUPPORTED

    def java_requirement(self) -> JavaRequirement:
        return JavaRequirement(
            min_major=17,
            preferred_major=21,
            notes="Vanilla 1.18+ typically needs Java 17+; newer versions may need 21.",
        )

    def detect_in_directory(self, server_dir: Path) -> bool:
        return (server_dir / "server.jar").is_file()

    def _default_jar_name(self, server_dir: Path) -> str:
        return "server.jar"

    def installation_requirements(self) -> list[str]:
        return [
            "Official vanilla server.jar",
            "Java 17+",
            "Accepted EULA",
        ]
