"""Validate check-project hotspot rules against supported configs (Windows-safe)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTAPD = ROOT / "pi-gen" / "stage-minebox" / "02-dedicated-hotspot" / "files" / "hostapd.conf"
DNSMASQ = ROOT / "pi-gen" / "stage-minebox" / "02-dedicated-hotspot" / "files" / "dnsmasq-minebox.conf"


class HotspotCheckTests(unittest.TestCase):
    def test_hostapd_supported_profile(self) -> None:
        text = HOSTAPD.read_text(encoding="utf-8")
        self.assertIn("ssid=MineBox-Setup", text)
        self.assertIn("hw_mode=g", text)
        self.assertIn("channel=11", text)
        self.assertIn("wpa=2", text)
        self.assertIn("rsn_pairwise=CCMP", text)
        # Stale check-project expected channel=6 — must not be required.
        self.assertNotRegex(text, r"(?m)^channel=6$")

    def test_dnsmasq_no_resolv_required(self) -> None:
        text = DNSMASQ.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^no-resolv$")
        self.assertIn("dhcp-option=option:dns-server,192.168.4.1", text)
        self.assertIn("bind-dynamic", text)

    def test_example_configs_present(self) -> None:
        self.assertTrue((ROOT / "config" / "minebox.example.toml").is_file())
        self.assertTrue((ROOT / "config" / "hardware.example.toml").is_file())

    def test_check_project_script_matches_supported_rules(self) -> None:
        script = (ROOT / "check-project.sh").read_text(encoding="utf-8")
        self.assertIn("channel=11", script)
        self.assertIn("no-resolv", script)
        self.assertNotIn("channel=6", script)
        # Must require no-resolv, not forbid it.
        self.assertFalse(re.search(r"!\s*grep\s+-Fqx\s+'no-resolv'", script))


if __name__ == "__main__":
    unittest.main()
