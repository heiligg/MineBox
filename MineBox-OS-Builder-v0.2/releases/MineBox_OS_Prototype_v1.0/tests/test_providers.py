"""Provider support-level tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from minecraft.providers import SupportLevel, get_provider, provider_capabilities
from minecraft.providers.base import ProviderValidation


class ProviderTests(unittest.TestCase):
    def test_paper_vanilla_supported(self) -> None:
        self.assertEqual(get_provider("paper").support_level, SupportLevel.SUPPORTED)
        self.assertEqual(get_provider("vanilla").support_level, SupportLevel.SUPPORTED)

    def test_forge_fabric_experimental(self) -> None:
        self.assertEqual(get_provider("forge").support_level, SupportLevel.EXPERIMENTAL)
        self.assertEqual(get_provider("fabric").support_level, SupportLevel.EXPERIMENTAL)

    def test_capabilities_public(self) -> None:
        caps = provider_capabilities()
        by_id = {row["id"]: row for row in caps}
        self.assertTrue(by_id["paper"]["v1_official"])
        self.assertFalse(by_id["forge"]["v1_official"])
        self.assertEqual(by_id["vanilla"]["status"], "SUPPORTED")

    def test_missing_jar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = get_provider("vanilla").validate(Path(tmp), java_path="java-not-real-xyz")
            self.assertIsInstance(result, ProviderValidation)
            self.assertFalse(result.jar_present)
            self.assertFalse(result.ok)

    def test_vanilla_detects_jar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server.jar").write_bytes(b"fake")
            self.assertTrue(get_provider("vanilla").detect_in_directory(root))


if __name__ == "__main__":
    unittest.main()
