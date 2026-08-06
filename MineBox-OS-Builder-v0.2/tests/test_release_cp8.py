"""Checkpoint 8 — release gates, version consistency, packaging exclusions."""

from __future__ import annotations

import ast
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
EXPECTED_VERSION = "1.0.0-prototype.1"

REQUIRED_DOCS = [
    "Installation.md",
    "Image_Build.md",
    "First_Boot.md",
    "User_Manual.md",
    "Administrator_Guide.md",
    "Hardware_Pinout.md",
    "Networking.md",
    "Hotspot.md",
    "Remote_Access.md",
    "Remote_Minecraft.md",
    "Backup_Restore.md",
    "Updates.md",
    "Troubleshooting.md",
    "Appliance_Recovery.md",
    "Developer_Guide.md",
    "Test_Plan.md",
    "Prototype_Hardware_Test_Plan.md",
    "Known_Limitations.md",
    "Release_Checklist.md",
    "Final_Release_Audit.md",
]


class VersionConsistencyTests(unittest.TestCase):
    def test_version_files(self) -> None:
        for path in (ROOT / "VERSION", APP / "VERSION"):
            self.assertTrue(path.is_file(), msg=str(path))
            self.assertEqual(path.read_text(encoding="utf-8").strip().splitlines()[0], EXPECTED_VERSION)

    def test_core_version_loader(self) -> None:
        os.environ.pop("MINEBOX_APP_DIR", None)
        import importlib
        import core.version as ver

        importlib.reload(ver)
        # Ensure loader sees app/VERSION
        self.assertEqual(ver.get_version(), EXPECTED_VERSION)

    def test_config_app_version(self) -> None:
        from config import APP_VERSION

        self.assertEqual(APP_VERSION, EXPECTED_VERSION)

    def test_no_stale_preview_version_in_active_config(self) -> None:
        text = (APP / "config.py").read_text(encoding="utf-8")
        self.assertNotIn("1.4.0-os-preview", text)
        health = (APP / "api" / "routes" / "health.py").read_text(encoding="utf-8")
        self.assertNotIn('API_VERSION = "0.1.0"', health)
        self.assertNotIn('version="0.2.0"', (APP / "api" / "server.py").read_text(encoding="utf-8"))


class SecurityReleaseTests(unittest.TestCase):
    def test_openapi_disabled_by_default(self) -> None:
        os.environ.pop("MINEBOX_DEV_MODE", None)
        os.environ.pop("MINEBOX_ENABLE_DOCS", None)
        from core.security import docs_enabled

        self.assertFalse(docs_enabled())

    def test_server_does_not_force_mock_hardware(self) -> None:
        text = (APP / "api" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn('setdefault("MINEBOX_FORCE_MOCK_HARDWARE"', text)
        self.assertNotIn("setdefault('MINEBOX_FORCE_MOCK_HARDWARE'", text)

    def test_no_default_admin_password_constant(self) -> None:
        auth = (APP / "services" / "auth.py").read_text(encoding="utf-8")
        self.assertNotRegex(auth, r"(?i)DEFAULT_ADMIN_PASSWORD\s*=")
        self.assertNotRegex(auth, r'password\s*=\s*["\']minebox["\']')

    def test_legacy_rcon_is_migration_marker_only(self) -> None:
        secrets = (APP / "core" / "secrets_store.py").read_text(encoding="utf-8")
        self.assertIn("LEGACY_HARDCODED_RCON", secrets)
        self.assertIn("MineBoxLocalRcon", secrets)
        # Must not assign as live default export in config
        cfg = (APP / "config.py").read_text(encoding="utf-8")
        self.assertNotRegex(cfg, r'^RCON_PASSWORD\s*=\s*["\']MineBoxLocalRcon["\']', re.M)

    def test_no_committed_private_keys(self) -> None:
        # Real PEM/OpenSSH headers (avoid matching this test's own string literals).
        patterns = (
            "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
        )
        skip_parts = {
            ".git",
            ".venv",
            ".build",
            "output",
            "releases",
            "__pycache__",
            ".test-runtime",
            "tests",
        }
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skip_parts for part in path.parts):
                continue
            if path.suffix.lower() in {".png", ".jpg", ".xz", ".img", ".zip", ".gz", ".pyc"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in patterns:
                self.assertNotIn(pat, text, msg=str(path))

    def test_first_boot_gating_module_present(self) -> None:
        self.assertTrue((APP / "services" / "first_boot.py").is_file())
        self.assertTrue((APP / "api" / "routes" / "first_boot.py").is_file())


class InstallerReleaseTests(unittest.TestCase):
    def test_install_sh_dry_run_and_idempotence_flags(self) -> None:
        text = (APP / "install.sh").read_text(encoding="utf-8")
        for flag in ("--dry-run", "--uninstall", "--skip-packages"):
            self.assertIn(flag, text)
        self.assertIn("VERSION", text)
        self.assertIn("preserving", text.lower())

    def test_sudoers_static_shape(self) -> None:
        text = (APP / "services" / "sudoers" / "minebox").read_text(encoding="utf-8")
        # Allow comment header; require allowlist line.
        self.assertRegex(text, r"(?m)^minebox ALL=\(root\) NOPASSWD:")
        self.assertIn("NOPASSWD:", text)
        self.assertNotIn("ALL=(ALL) NOPASSWD: ALL", text)
        # Args must be explicitly allowed (sudo treats script path as an argument).
        self.assertIn(
            "/usr/bin/python3 /opt/minebox/scripts/minebox_ensure_java.py *",
            text,
        )
        self.assertIn("/usr/local/sbin/minebox-ensure-java *", text)

    def test_systemd_units_parse_keys(self) -> None:
        for name in (
            "minebox-api.service",
            "minebox-ui.service",
            "minebox-display.service",
            "minecraft.service",
            "minebox-captive.service",
        ):
            path = APP / "services" / name
            text = path.read_text(encoding="utf-8")
            self.assertIn("[Unit]", text)
            self.assertIn("[Service]", text)
            self.assertIn("[Install]", text)
            self.assertIn("ExecStart=", text)
            self.assertNotRegex(text, r"(?i)ExecStart.*=.*\bsleep\b")


class PackagingDocTests(unittest.TestCase):
    def test_required_docs_exist(self) -> None:
        docs = ROOT / "docs" / "v1"
        for name in REQUIRED_DOCS:
            self.assertTrue((docs / name).is_file(), msg=name)
        self.assertTrue((ROOT / "README.md").is_file())
        self.assertTrue((ROOT / "CHANGELOG.md").is_file())

    def test_doc_links_to_existing_files(self) -> None:
        docs = ROOT / "docs" / "v1"
        link_re = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
        for path in docs.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for _label, target in link_re.findall(text):
                if target.startswith("http"):
                    continue
                # strip anchors
                rel = target.split("#", 1)[0]
                if not rel:
                    continue
                dest = (path.parent / rel).resolve()
                self.assertTrue(dest.is_file(), msg=f"{path.name} -> {target}")

    def test_first_boot_check_exists(self) -> None:
        self.assertTrue((APP / "scripts" / "minebox_first_boot_check.py").is_file())

    def test_curses_fallback_exists(self) -> None:
        self.assertTrue((APP / "main.py").is_file())
        ui = (APP / "services" / "minebox-ui.service").read_text(encoding="utf-8")
        self.assertIn("/opt/minebox/main.py", ui)

    def test_display_service_fallback_documented(self) -> None:
        disp = (APP / "services" / "minebox-display.service").read_text(encoding="utf-8")
        self.assertIn("xinit", disp)
        self.assertIn("Restart=on-failure", disp)

    def test_route_security_inventory(self) -> None:
        inv = ROOT / "docs" / "v1" / "API_Route_Security.md"
        self.assertTrue(inv.is_file())
        text = inv.read_text(encoding="utf-8")
        self.assertGreater(len(text), 200)

    def test_provider_labels(self) -> None:
        from services import servers  # noqa: F401
        # Config example lists providers
        example = (ROOT / "config" / "minebox.example.toml").read_text(encoding="utf-8")
        self.assertIn("paper", example.lower())


class NftablesAndHotspotTests(unittest.TestCase):
    def test_nftables_policy_generates(self) -> None:
        from networking.firewall import build_policy_for_roles

        policy = build_policy_for_roles("wlan1", has_uplink=False)
        self.assertTrue(policy["validation"]["ok"], msg=policy["validation"])
        self.assertIn("wlan1", policy["ruleset"])

    def test_dynamic_hotspot_render_dry_run(self) -> None:
        os.environ["MINEBOX_APP_DIR"] = str(APP)
        import importlib.util

        path = APP / "scripts" / "minebox_render_hotspot_configs.py"
        spec = importlib.util.spec_from_file_location("render_cp8", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        code = mod.main(["--dry-run", "--iface", "wlan1", "--skip-nft"])
        self.assertEqual(code, 0)


class ReleaseExclusionPolicyTests(unittest.TestCase):
    """Documents what the packager must exclude — validated when archive exists."""

    FORBIDDEN_NAME_PARTS = {
        ".git",
        ".venv",
        "__pycache__",
        ".test-runtime",
        ".build",
        "auth.json",
    }

    def test_packager_script_exists(self) -> None:
        self.assertTrue((ROOT / "scripts" / "build_release_package.py").is_file())

    def test_if_release_tree_exists_exclusions(self) -> None:
        release = ROOT / "releases" / "MineBox_OS_Prototype_v1.0"
        if not release.is_dir():
            self.skipTest("release tree not built yet")
        for path in release.rglob("*"):
            parts = set(path.parts)
            for bad in self.FORBIDDEN_NAME_PARTS:
                self.assertNotIn(bad, parts, msg=str(path))
            if path.name.endswith((".pyc", ".backup", ".bak")):
                self.fail(f"forbidden file in release: {path}")


if __name__ == "__main__":
    unittest.main()
