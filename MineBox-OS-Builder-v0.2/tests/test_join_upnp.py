"""Join / UPnP helper tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from services import join_access
from services.system import CommandResult


class JoinUpnpTests(unittest.TestCase):
    def test_parses_external_ip(self) -> None:
        text = "ExternalIPAddress = 192.168.0.244\nexternal 192.168.0.244:25565 TCP is redirected"
        self.assertEqual(join_access._parse_upnp_external_ip(text), "192.168.0.244")

    def test_private_ip(self) -> None:
        self.assertTrue(join_access._private_ip("192.168.0.244"))
        self.assertFalse(join_access._private_ip("205.237.131.135"))

    def test_enable_binds_to_lan_and_maps_tcp(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command, timeout=30):
            calls.append(list(command))
            if "-a" in command:
                return CommandResult(
                    True,
                    stdout=(
                        "ExternalIPAddress = 8.8.8.8\n"
                        "external 8.8.8.8:25565 TCP is redirected to internal "
                        "192.168.86.226:25565"
                    ),
                )
            return CommandResult(True, stdout="ok")

        with mock.patch.object(join_access, "lan_ip", return_value="192.168.86.226"), mock.patch.object(
            join_access, "game_port", return_value=25565
        ), mock.patch.object(
            join_access, "_upnp_binaries", return_value=["/usr/bin/upnpc"]
        ), mock.patch.object(
            join_access, "public_ip", return_value="8.8.8.8"
        ), mock.patch.object(
            join_access, "_save_upnp_state"
        ), mock.patch(
            "services.join_access.run", side_effect=fake_run
        ):
            result = join_access.enable_upnp()
        self.assertTrue(result["ok"])
        self.assertTrue(result["mapped"])
        self.assertTrue(result["internet_reachable"])
        self.assertTrue(any("-m" in call and "192.168.86.226" in call for call in calls))
        self.assertTrue(any("tcp" in call and "-a" in call for call in calls))

    def test_enable_reports_double_nat(self) -> None:
        def fake_run(command, timeout=30):
            return CommandResult(
                True,
                stdout=(
                    "ExternalIPAddress = 192.168.0.244\n"
                    "external 192.168.0.244:25565 TCP is redirected to internal "
                    "192.168.86.226:25565"
                ),
            )

        with mock.patch.object(join_access, "lan_ip", return_value="192.168.86.226"), mock.patch.object(
            join_access, "game_port", return_value=25565
        ), mock.patch.object(
            join_access, "_upnp_binaries", return_value=["/usr/bin/upnpc"]
        ), mock.patch.object(
            join_access, "public_ip", return_value="205.237.131.135"
        ), mock.patch.object(
            join_access, "_save_upnp_state"
        ), mock.patch(
            "services.join_access.run", side_effect=fake_run
        ):
            result = join_access.enable_upnp()
        self.assertTrue(result["ok"])
        self.assertTrue(result["double_nat"])
        self.assertFalse(result["internet_reachable"])
        self.assertIn("another router", result["message"])


if __name__ == "__main__":
    unittest.main()
