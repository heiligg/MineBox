"""Secret handling and redaction tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import secrets_store


class SecretsTests(unittest.TestCase):
    def test_redact_known_secrets(self) -> None:
        text = "wpa_passphrase=mineboxsetup rcon.password=MineBoxLocalRcon token=abc"
        redacted = secrets_store.redact_secrets(text)
        self.assertNotIn("mineboxsetup", redacted)
        self.assertNotIn("MineBoxLocalRcon", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_server_rcon_not_legacy_hardcoded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server_dir = Path(tmp)
            password = secrets_store.get_or_create_server_rcon_password(server_dir)
            self.assertNotEqual(password, secrets_store.LEGACY_HARDCODED_RCON)
            self.assertGreaterEqual(len(password), 16)
            again = secrets_store.get_or_create_server_rcon_password(server_dir)
            self.assertEqual(password, again)

    def test_rotates_legacy_hardcoded_rcon_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server_dir = Path(tmp)
            legacy = server_dir / ".minebox-rcon-password"
            legacy.write_text(secrets_store.LEGACY_HARDCODED_RCON + "\n", encoding="utf-8")
            password = secrets_store.get_or_create_server_rcon_password(server_dir)
            self.assertNotEqual(password, secrets_store.LEGACY_HARDCODED_RCON)

    def test_bootstrap_hotspot_detected(self) -> None:
        self.assertTrue(secrets_store.is_bootstrap_hotspot_psk("mineboxsetup"))
        self.assertFalse(secrets_store.is_bootstrap_hotspot_psk("unique-psk-value"))

    def test_no_hardcoded_rcon_in_active_config_module(self) -> None:
        import config

        source = Path(config.__file__).read_text(encoding="utf-8")
        self.assertNotIn('RCON_PASSWORD = "MineBoxLocalRcon"', source)


if __name__ == "__main__":
    unittest.main()
