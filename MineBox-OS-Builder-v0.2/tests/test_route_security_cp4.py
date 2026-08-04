"""Route security inventory smoke checks."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RouteSecurityTests(unittest.TestCase):
    def test_docs_disabled_by_default(self) -> None:
        os.environ.pop("MINEBOX_ENABLE_DOCS", None)
        os.environ.pop("MINEBOX_DEV_MODE", None)
        import importlib
        import sys

        app_dir = str(ROOT / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        from core import security

        importlib.reload(security)
        self.assertFalse(security.docs_enabled())

    def test_docs_enabled_in_dev(self) -> None:
        os.environ["MINEBOX_DEV_MODE"] = "1"
        import importlib
        import sys

        app_dir = str(ROOT / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        from core import security

        importlib.reload(security)
        self.assertTrue(security.docs_enabled())

    def test_no_cors_middleware(self) -> None:
        text = (ROOT / "app" / "api" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("CORSMiddleware", text)

    def test_inventory_doc_exists(self) -> None:
        path = ROOT / "docs" / "v1" / "API_Route_Security.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("privileged/destructive", text)
        self.assertIn("/api/v1/minecraft/stop", text)

    def test_cp4_security_docs_exist(self) -> None:
        docs = ROOT / "docs" / "v1"
        for name in (
            "Authentication.md",
            "First_Boot.md",
            "Security_Model.md",
            "Web_Dashboard.md",
            "Factory_Reset.md",
            "Privileged_Operations.md",
            "API_Route_Security.md",
        ):
            self.assertTrue((docs / name).is_file(), msg=name)

    def test_sudoers_includes_os_password_helper(self) -> None:
        canonical = ROOT / "app" / "services" / "sudoers" / "minebox"
        self.assertTrue(canonical.is_file())
        self.assertIn("minebox_set_os_password.py", canonical.read_text(encoding="utf-8"))
        install_sh = (ROOT / "app" / "install.sh").read_text(encoding="utf-8")
        self.assertIn("services/sudoers/minebox", install_sh)
        chroot = (
            ROOT
            / "pi-gen"
            / "stage-minebox"
            / "00-install-minebox"
            / "00-run-chroot.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("services/sudoers/minebox", chroot)
        self.assertIn("minebox_set_os_password.py", chroot)

    def test_destructive_routes_require_confirm_in_code(self) -> None:
        minecraft = (ROOT / "app" / "api" / "routes" / "minecraft.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Stop requires confirm=true", minecraft)
        self.assertIn("Restart requires confirm=true", minecraft)
        system = (ROOT / "app" / "api" / "routes" / "system.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Shutdown requires confirm=true", system)
        self.assertIn("Reboot requires confirm=true", system)


if __name__ == "__main__":
    unittest.main()
