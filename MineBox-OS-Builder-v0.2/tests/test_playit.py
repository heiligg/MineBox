"""playit.gg helper parsing tests."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from services import playit


class PlayitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        folder = Path(self._temp.name)
        self._dir = mock.patch.object(playit, "DATA_DIR", folder)
        self._config = mock.patch.object(playit, "CONFIG_FILE", folder / "playit.toml")
        self._log = mock.patch.object(playit, "LOG_FILE", folder / "playit.log")
        self._dir.start()
        self._config.start()
        self._log.start()
        playit.CONFIG_FILE.write_text("", encoding="utf-8")
        playit.LOG_FILE.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self._log.stop()
        self._config.stop()
        self._dir.stop()
        self._temp.cleanup()

    def test_reads_claim_url_from_log(self) -> None:
        playit.LOG_FILE.write_text(
            "Visit https://playit.gg/claim/abc123 to continue\n",
            encoding="utf-8",
        )
        self.assertEqual(playit.claim_url(), "https://playit.gg/claim/abc123")

    def test_reads_secret_and_address(self) -> None:
        playit.CONFIG_FILE.write_text('secret_key = "super-secret-key"\n', encoding="utf-8")
        self.assertEqual(playit.secret_key(), "super-secret-key")
        with mock.patch.object(playit, "_agent_running", return_value=True), mock.patch.object(
            playit, "_join_address", return_value="abc.gl.join.playit.gg:25565"
        ):
            status = playit.status()
        self.assertEqual(status["state"], "connected")
        self.assertEqual(status["address"], "abc.gl.join.playit.gg:25565")

    def test_collects_display_address(self) -> None:
        addresses = playit._collect_addresses(
            {
                "tunnels": [
                    {"display_address": "minebox.gl.join.playit.gg:25565", "tunnel_type": "minecraft-java"}
                ]
            }
        )
        self.assertEqual(addresses[0], "minebox.gl.join.playit.gg:25565")


if __name__ == "__main__":
    unittest.main()
