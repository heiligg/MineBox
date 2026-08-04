"""First-boot incomplete bootstrap state tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import bootstrap


class BootstrapTests(unittest.TestCase):
    def test_incomplete_state_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MINEBOX_RUNTIME_DIR"] = tmp
            with mock.patch("core.bootstrap._auth_configured", return_value=False), mock.patch(
                "core.bootstrap._setup_marker_present", return_value=False
            ):
                state = bootstrap.get_bootstrap_state()
            self.assertFalse(state.first_boot_complete)
            self.assertTrue(state.credentials_rotation_required)
            self.assertIn("incomplete", state.message.lower())
            public = state.to_public_dict()
            self.assertFalse(public["secrets_exposed"])
            self.assertNotIn("password", public)


if __name__ == "__main__":
    unittest.main()
