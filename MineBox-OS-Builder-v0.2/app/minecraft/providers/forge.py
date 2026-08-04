from __future__ import annotations

from pathlib import Path

from minecraft.providers.base import BaseProvider, JavaRequirement, SupportLevel


class ForgeProvider(BaseProvider):
    """Preserved Forge support — experimental until integration tests pass."""

    name = "forge"
    support_level = SupportLevel.EXPERIMENTAL

    def java_requirement(self) -> JavaRequirement:
        return JavaRequirement(
            min_major=8,
            preferred_major=17,
            notes="Forge Java major depends on Minecraft version (1.12→8, modern→17/21).",
        )

    def detect_in_directory(self, server_dir: Path) -> bool:
        if (server_dir / ".minebox-forge-args").is_file():
            return True
        if (server_dir / "run.sh").is_file() and (server_dir / "libraries").is_dir():
            return True
        if any(server_dir.glob("forge-*-shim.jar")):
            return True
        return any(
            path.is_file() and "installer" not in path.name
            for path in server_dir.glob("forge-*.jar")
        )

    def installation_requirements(self) -> list[str]:
        return [
            "Forge installer / unix_args launch files",
            "Matching Java for the Minecraft version",
            "Accepted EULA",
            "Experimental on MineBox Prototype v1",
        ]

    def supports_update(self) -> bool:
        return False

    def health_hints(self) -> list[str]:
        return ["Done (", "For help, type", "Server thread/", "FML"]
