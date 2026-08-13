"""Nested folder uploads keep relative paths and stay inside the server root."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FilesUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        app_dir = str(ROOT / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        sys.modules.setdefault("fastapi", type(sys)("fastapi")).UploadFile = object

    def test_nested_relative_path(self) -> None:
        from services.files import _sanitize_nested_path, _upload_relative

        self.assertEqual(
            _upload_relative("pack.mcmeta", "datapacks/my pack/pack.mcmeta"),
            "datapacks/my pack/pack.mcmeta",
        )
        self.assertEqual(_upload_relative("mod.jar", None), "mod.jar")
        self.assertEqual(
            _sanitize_nested_path("file.txt", "mods/jei/file.txt", "file.txt"),
            "mods/jei/file.txt",
        )
        from services.files import decode_rel_token

        self.assertEqual(
            decode_rel_token("bW9kcy9qZWkvZmlsZS50eHQ"),
            "mods/jei/file.txt",
        )

    def test_rejects_escape(self) -> None:
        from services.files import FilesError, _upload_relative

        self.assertEqual(_upload_relative("secret.txt", "../secret.txt"), "secret.txt")
        with self.assertRaises(FilesError):
            _upload_relative(None, "../secret.txt")
        with self.assertRaises(FilesError):
            _upload_relative("", "mods/")

    def test_find_world_root_nested_save(self) -> None:
        from services.files import find_world_root

        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            world = staging / "My Survival"
            (world / "region").mkdir(parents=True)
            (world / "level.dat").write_bytes(b"dat")
            (world / "region" / "r.0.0.mca").write_bytes(b"mca")
            self.assertEqual(find_world_root(staging), world)

    def test_zip_slip_rejected(self) -> None:
        from services.files import FilesError, _safe_extract_zip

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.zip"
            dest = Path(tmp) / "out"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../secret.txt", "nope")
            with self.assertRaises(FilesError):
                _safe_extract_zip(archive, dest)


if __name__ == "__main__":
    unittest.main()
