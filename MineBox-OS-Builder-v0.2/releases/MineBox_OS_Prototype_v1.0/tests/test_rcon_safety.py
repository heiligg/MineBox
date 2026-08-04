"""RCON allowlist and secret redaction tests."""

from __future__ import annotations

import unittest

from core.secrets_store import redact_secrets
from services.rcon_safety import check_command


class RconSafetyTests(unittest.TestCase):
    def test_allow_save_commands(self) -> None:
        for cmd in ("save-all", "save-all flush", "save-off", "save-on", "list", "stop"):
            self.assertTrue(check_command(cmd).allowed, cmd)

    def test_deny_shell_meta(self) -> None:
        self.assertFalse(check_command("list; rm -rf /").allowed)
        self.assertFalse(check_command("say $(reboot)").allowed)

    def test_deny_unknown(self) -> None:
        self.assertFalse(check_command("execute as @a run kill").allowed)

    def test_status_redaction(self) -> None:
        text = "rcon.password=MineBoxLocalRcon hotspot=mineboxsetup"
        red = redact_secrets(text)
        self.assertNotIn("MineBoxLocalRcon", red)
        self.assertNotIn("mineboxsetup", red)


if __name__ == "__main__":
    unittest.main()
