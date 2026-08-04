from __future__ import annotations

from pathlib import Path

from minecraft.providers.base import BaseProvider, JavaRequirement, SupportLevel


class PaperProvider(BaseProvider):
    name = "paper"
    support_level = SupportLevel.SUPPORTED

    def java_requirement(self) -> JavaRequirement:
        return JavaRequirement(
            min_major=17,
            preferred_major=21,
            notes="Paper modern builds require Java 17+.",
        )

    def detect_in_directory(self, server_dir: Path) -> bool:
        if (server_dir / "paper.jar").is_file():
            return True
        if (server_dir / "server.jar").is_file():
            # Paper installs often still named server.jar
            marker = server_dir / "version_history.json"
            cache = server_dir / "cache"
            return marker.is_file() or cache.is_dir()
        return any(server_dir.glob("paper-*.jar"))

    def _default_jar_name(self, server_dir: Path) -> str:
        if (server_dir / "paper.jar").is_file():
            return "paper.jar"
        papers = sorted(server_dir.glob("paper-*.jar"))
        if papers:
            return papers[-1].name
        return "server.jar"

    def installation_requirements(self) -> list[str]:
        return [
            "Paper server jar",
            "Java 17+",
            "Accepted EULA",
        ]

    def health_hints(self) -> list[str]:
        return ["Done (", "For help, type", "Timings Reset"]
