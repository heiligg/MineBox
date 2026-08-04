"""Checkpoint 6 — interface roles, firewall, Tailscale, support bundle."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NetworkCp6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MINEBOX_RUNTIME_DIR"] = self.tmp.name
        os.environ["MINEBOX_NETWORK_ROLES_FILE"] = str(Path(self.tmp.name) / "roles.json")
        os.environ["MINEBOX_REMOTE_ACCESS_FILE"] = str(Path(self.tmp.name) / "remote.json")
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        os.environ.pop("MINEBOX_HOTSPOT_IFACE", None)
        import sys

        app_dir = str(ROOT / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _sysfs(self, layout: dict[str, dict]) -> Path:
        root = Path(self.tmp.name) / "sysnet"
        for name, meta in layout.items():
            base = root / name
            base.mkdir(parents=True)
            (base / "address").write_text(meta.get("mac", "00:00:00:00:00:00") + "\n")
            (base / "type").write_text("1\n")
            if meta.get("wifi"):
                (base / "wireless").mkdir()
            if meta.get("usb"):
                device = base / "device"
                device.mkdir()
                # Fake USB path markers
                (device / "idVendor").write_text(meta.get("vid", "0bda") + "\n")
                (device / "idProduct").write_text(meta.get("pid", "8179") + "\n")
        return root

    def test_role_onboard_and_usb(self) -> None:
        from networking import roles

        sysfs = self._sysfs(
            {
                "wlan0": {"wifi": True, "mac": "aa:aa:aa:aa:aa:01"},
                "wlan1": {"wifi": True, "usb": True, "mac": "aa:aa:aa:aa:aa:02"},
                "eth0": {"mac": "aa:aa:aa:aa:aa:03"},
            }
        )
        os.environ["MINEBOX_HOTSPOT_IFACE"] = ""
        # prefer onboard via env-less resolve: set role through monkeypatch of overrides
        ifaces = roles.discover_interfaces(sysfs)
        self.assertEqual(len(ifaces), 3)
        assignment = roles.resolve_roles(ifaces, persist=True)
        self.assertIsNotNone(assignment.hotspot)
        self.assertNotEqual(assignment.hotspot, assignment.wifi_uplink)
        self.assertEqual(assignment.ethernet_uplink, "eth0")

    def test_manual_override(self) -> None:
        from networking import roles

        sysfs = self._sysfs(
            {
                "wlan0": {"wifi": True, "mac": "aa:aa:aa:aa:aa:01"},
                "wlan1": {"wifi": True, "usb": True, "mac": "aa:aa:aa:aa:aa:02"},
            }
        )
        os.environ["MINEBOX_HOTSPOT_IFACE"] = "wlan1"
        assignment = roles.resolve_roles(roles.discover_interfaces(sysfs), persist=True)
        self.assertEqual(assignment.hotspot, "wlan1")
        self.assertEqual(assignment.source, "manual_override")

    def test_stale_assignment_no_silent_reassign(self) -> None:
        from networking import roles

        sysfs = self._sysfs({"wlan0": {"wifi": True, "mac": "aa:aa:aa:aa:aa:01"}})
        roles.roles_path().write_text(
            '{"hotspot":"wlan9","hotspot_identity":"mac:de:ad:be:ef:00:01","source":"persisted_name"}',
            encoding="utf-8",
        )
        os.environ.pop("MINEBOX_HOTSPOT_IFACE", None)
        assignment = roles.resolve_roles(
            roles.discover_interfaces(sysfs), persist=False, allow_silent_reassign=False
        )
        self.assertIn("stale_hotspot_assignment", assignment.unresolved)
        self.assertTrue(any("silent reassignment" in w for w in assignment.warnings))

    def test_missing_adapter(self) -> None:
        from networking import roles

        sysfs = self._sysfs({"eth0": {"mac": "aa:aa:aa:aa:aa:03"}})
        assignment = roles.resolve_roles(roles.discover_interfaces(sysfs), persist=False)
        self.assertIn("no_wifi_adapter", assignment.unresolved)

    def test_firewall_sharing_toggle(self) -> None:
        from networking import firewall

        with_sharing = firewall.generate_nftables(hotspot_iface="wlan0", internet_sharing=True)
        without = firewall.generate_nftables(hotspot_iface="wlan0", internet_sharing=False)
        self.assertIn("masquerade", with_sharing)
        self.assertNotIn("masquerade", without)
        self.assertTrue(firewall.validate_nftables_text(with_sharing)["ok"])
        self.assertTrue(firewall.validate_nftables_text(without)["ok"])
        self.assertIn("25575", with_sharing)
        self.assertIn("policy drop", with_sharing)
        self.assertIn('iifname "lo" accept', with_sharing)

    def test_firewall_renamed_iface(self) -> None:
        from networking import firewall

        text = firewall.generate_nftables(hotspot_iface="wlx1234", internet_sharing=True)
        self.assertIn("wlx1234", text)
        self.assertTrue(firewall.validate_nftables_text(text)["ok"])

    def test_recovery_restart_limit(self) -> None:
        from networking import recovery

        for _ in range(recovery.MAX_BURST):
            recovery.record_attempt("hostapd_restart")
        allowed, retry = recovery.can_attempt("hostapd_restart")
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)
        result = recovery.manual_retry()
        self.assertFalse(result["ok"])

    def test_tailscale_disabled_by_default(self) -> None:
        from networking.remote_access import TailscaleRemoteAccessProvider

        provider = TailscaleRemoteAccessProvider()
        status = provider.status(authenticated=True)
        self.assertIn(status.state, {"DISABLED", "NOT_INSTALLED"})
        self.assertFalse(status.expose_dashboard)
        self.assertFalse(status.expose_minecraft)

    def test_tailscale_key_validation_and_no_injection(self) -> None:
        from networking.remote_access import validate_auth_key

        with self.assertRaises(ValueError):
            validate_auth_key("short")
        with self.assertRaises(ValueError):
            validate_auth_key("tskey-auth-abc; rm -rf /")
        key = validate_auth_key("tskey-auth-" + ("a" * 24))
        self.assertTrue(key.startswith("tskey-"))

    def test_tailscale_disable_requires_confirm(self) -> None:
        from networking.remote_access import TailscaleRemoteAccessProvider

        provider = TailscaleRemoteAccessProvider()
        with self.assertRaises(ValueError):
            provider.disable(confirm=False)

    def test_support_bundle_redacts_secrets(self) -> None:
        from networking.support_bundle import build_network_support_bundle

        os.environ["MINEBOX_INTERNET_SHARING"] = "0"
        bundle = build_network_support_bundle()
        text = str(bundle)
        self.assertNotIn("mineboxsetup", text.lower())
        self.assertIn("role_assignment", bundle)
        self.assertIn("nftables_summary", bundle)
        self.assertIn("tailscale", bundle)
        self.assertIsNone(bundle.get("auth_key"))

    def test_hotspot_without_uplink_policy(self) -> None:
        from networking import firewall

        policy = firewall.build_policy_for_roles("wlan0", has_uplink=False)
        # Sharing configured may be true, but active requires uplink.
        self.assertFalse(policy["internet_sharing_active"])
        self.assertNotIn("masquerade", policy["ruleset"])

    def test_docs_exist(self) -> None:
        docs = ROOT / "docs" / "v1"
        for name in (
            "Networking.md",
            "Hotspot.md",
            "Interface_Roles.md",
            "Firewall.md",
            "Internet_Sharing.md",
            "Network_Recovery.md",
            "Remote_Access.md",
            "Tailscale.md",
            "Remote_Minecraft.md",
            "Support_Bundle.md",
        ):
            self.assertTrue((docs / name).is_file(), msg=name)


if __name__ == "__main__":
    unittest.main()
