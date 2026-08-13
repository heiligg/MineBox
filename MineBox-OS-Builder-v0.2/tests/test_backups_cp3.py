"""Backup/restore hardening tests."""

from __future__ import annotations

import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import backups
from services.operations import reset_coordinator
from services.system import CommandResult


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.world = self.root / "world"
        self.world.mkdir()
        (self.world / "level.dat").write_bytes(b"dat")
        (self.world / "region").mkdir()
        (self.world / "region" / "r.0.0.mca").write_bytes(b"region")
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir()
        os.environ["MINEBOX_RUNTIME_DIR"] = str(self.root / "runtime")
        Path(os.environ["MINEBOX_RUNTIME_DIR"]).mkdir(parents=True, exist_ok=True)
        reset_coordinator()

        self.patches = [
            mock.patch.object(backups, "_minecraft_dir", return_value=self.root),
            mock.patch.object(backups, "_backup_dir", return_value=self.backup_dir),
            mock.patch.object(backups, "_world_dir", return_value=self.world),
            mock.patch.object(backups, "_preserve_last_backup", return_value=True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        reset_coordinator()
        self.tmp.cleanup()

    def test_stopped_server_backup_checksum(self) -> None:
        with mock.patch.object(
            backups.minecraft, "is_running", return_value=False
        ), mock.patch(
            "services.lifecycle.get_lifecycle"
        ) as life:
            life.return_value.begin_backup_state.return_value = None
            life.return_value.end_backup_state.return_value = None
            with mock.patch("services.servers.active_server", return_value=None), mock.patch(
                "services.minecraft.version", return_value="1.20.1"
            ):
                result = backups.create_backup(retention=10)
        self.assertIn("checksum_sha256", result)
        path = self.backup_dir / result["filename"]
        self.assertTrue(path.is_file())
        self.assertTrue(Path(str(path) + ".sha256").is_file())
        backups.validate_backup_archive(result["filename"])

    def test_autosave_restored_after_failure(self) -> None:
        calls: list[str] = []

        def fake_send(cmd: str, *args, **kwargs):
            calls.append(cmd)
            if cmd == "save-off":
                return CommandResult(True, "off")
            if cmd == "save-on":
                return CommandResult(True, "on")
            if cmd.startswith("save-all"):
                return CommandResult(True, "saved")
            return CommandResult(True, "ok")

        with mock.patch.object(backups.minecraft, "is_running", return_value=True), mock.patch.object(
            backups.minecraft, "save_world", return_value=CommandResult(True, "saved")
        ), mock.patch(
            "services.lifecycle.get_lifecycle"
        ) as life, mock.patch(
            "services.minecraft_health.collect_health"
        ) as health, mock.patch(
            "services.rcon.send", side_effect=fake_send
        ), mock.patch(
            "services.servers.active_server", return_value=None
        ):
            from services.minecraft_health import HealthCheckResult
            from core.states import HealthEvidence

            health.return_value = HealthCheckResult(
                healthy=True,
                evidence=HealthEvidence(port_listening=True, process_present=True),
                phase="running",
            )
            life.return_value.begin_backup_state.side_effect = Exception("boom")
            with self.assertRaises(backups.BackupError):
                backups.create_backup()
        # save-off may not have been reached; ensure we never leave disabled without on.
        if "save-off" in calls:
            self.assertIn("save-on", calls)

    def test_preserve_only_backup(self) -> None:
        archive = self.backup_dir / "world-test.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(self.world, arcname="world")
        with self.assertRaises(backups.BackupError):
            backups.delete_backup(archive.name)

    def test_restore_requires_confirm(self) -> None:
        with self.assertRaises(backups.BackupError) as ctx:
            backups.restore_backup("world-x.tar.gz", confirm=False)
        self.assertIn("confirm=true", str(ctx.exception))

    def test_path_traversal_rejected(self) -> None:
        with self.assertRaises(backups.BackupError):
            backups.get_backup_path("../etc/passwd")

    def test_retention_keeps_last(self) -> None:
        for i in range(3):
            path = self.backup_dir / f"world-old-{i}.tar.gz"
            path.write_bytes(b"x")
        removed = backups._remove_old_backups(retention=1)
        # With preserve_last_backup, never remove down to zero.
        self.assertGreaterEqual(len(backups._backup_files()), 1)
        self.assertTrue(removed or len(backups._backup_files()) >= 1)


class PerServerBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.world = self.root / "world"
        self.world.mkdir()
        os.environ["MINEBOX_RUNTIME_DIR"] = str(self.root / "runtime")
        Path(os.environ["MINEBOX_RUNTIME_DIR"]).mkdir(parents=True, exist_ok=True)
        self.patches = [
            mock.patch.object(backups, "_minecraft_dir", return_value=self.root),
            mock.patch.object(backups, "_world_dir", return_value=self.world),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in self.patches:
            patch.stop()
        self.tmp.cleanup()

    def test_lists_only_active_server_backups(self) -> None:
        alpha = self.root / "backups" / "alpha"
        beta = self.root / "backups" / "beta"
        alpha.mkdir(parents=True)
        beta.mkdir(parents=True)
        (alpha / "world-alpha-1.tar.gz").write_bytes(b"a")
        (beta / "world-beta-1.tar.gz").write_bytes(b"b")
        active = mock.Mock(server_id="alpha", name="Alpha")
        with mock.patch.object(backups.servers, "active_server", return_value=active):
            names = [path.name for path in backups._backup_files()]
        self.assertEqual(names, ["world-alpha-1.tar.gz"])

    def test_migrates_legacy_shared_backups(self) -> None:
        shared = self.root / "backups"
        shared.mkdir()
        legacy = shared / "world-alpha-old.tar.gz"
        legacy.write_bytes(b"old")
        other = shared / "world-beta-old.tar.gz"
        other.write_bytes(b"other")
        active = mock.Mock(server_id="alpha", name="Alpha")
        with mock.patch.object(backups.servers, "active_server", return_value=active):
            names = [path.name for path in backups._backup_files()]
        self.assertEqual(names, ["world-alpha-old.tar.gz"])
        self.assertTrue((shared / "alpha" / "world-alpha-old.tar.gz").is_file())
        self.assertTrue(other.is_file())


if __name__ == "__main__":
    unittest.main()
