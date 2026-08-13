"""Nested folder uploads keep relative paths and stay inside the server root."""

from __future__ import annotations

import os
import sys
import unittest
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
        from services.files import _upload_relative

        self.assertEqual(
            _upload_relative("pack.mcmeta", "datapacks/my pack/pack.mcmeta"),
            "datapacks/my pack/pack.mcmeta",
        )
        self.assertEqual(_upload_relative("mod.jar", None), "mod.jar")

    def test_rejects_escape(self) -> None:
        from services.files import FilesError, _upload_relative

        with self.assertRaises(FilesError):
            _upload_relative("secret.txt", "../secret.txt")
        with self.assertRaises(FilesError):
            _upload_relative("", "mods/")


if __name__ == "__main__":
    unittest.main()
