"""Player UUID migration when online-mode changes."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from services import players


class PlayerUuidMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.world = self.root / "world"
        self.playerdata = self.world / "playerdata"
        self.stats = self.world / "stats"
        self.playerdata.mkdir(parents=True)
        self.stats.mkdir()
        os.environ["MINEBOX_RUNTIME_DIR"] = str(self.root / "runtime")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_copies_online_inventory_to_offline_uuid(self) -> None:
        online_uuid = "54e4ce44-5ff5-456f-9827-e41c04845ed9"
        offline_uuid = players._offline_uuid("grant236")
        (self.playerdata / f"{online_uuid}.dat").write_bytes(b"inventory-data" * 20)
        (self.playerdata / f"{offline_uuid}.dat").write_bytes(b"empty")
        (self.stats / f"{online_uuid}.json").write_text("{}", encoding="utf-8")
        (self.root / "usercache.json").write_text(
            json.dumps(
                [
                    {"name": "grant236", "uuid": online_uuid},
                    {"name": "grant236", "uuid": offline_uuid},
                ]
            ),
            encoding="utf-8",
        )
        (self.root / "server.properties").write_text(
            "online-mode=false\n",
            encoding="utf-8",
        )

        moved = players.migrate_playerdata_for_online_mode(self.root)
        self.assertTrue(moved)
        restored = (self.playerdata / f"{offline_uuid}.dat").read_bytes()
        self.assertIn(b"inventory-data", restored)
        self.assertTrue((self.stats / f"{offline_uuid}.json").is_file())

    def test_leaves_larger_file_alone(self) -> None:
        online_uuid = "54e4ce44-5ff5-456f-9827-e41c04845ed9"
        offline_uuid = players._offline_uuid("grant236")
        (self.playerdata / f"{online_uuid}.dat").write_bytes(b"small")
        (self.playerdata / f"{offline_uuid}.dat").write_bytes(b"already-has-more-stuff")
        (self.root / "usercache.json").write_text(
            json.dumps([{"name": "grant236", "uuid": online_uuid}]),
            encoding="utf-8",
        )
        (self.root / "server.properties").write_text(
            "online-mode=false\n",
            encoding="utf-8",
        )
        players.migrate_playerdata_for_online_mode(self.root)
        self.assertEqual(
            (self.playerdata / f"{offline_uuid}.dat").read_bytes(),
            b"already-has-more-stuff",
        )


if __name__ == "__main__":
    unittest.main()
