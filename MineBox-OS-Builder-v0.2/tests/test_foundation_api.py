"""Foundation status service — no secrets in responses."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FoundationStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        os.environ["MINEBOX_HARDWARE_PROFILE"] = "mock"
        os.environ["MINEBOX_CONFIG"] = str(ROOT / "config" / "minebox.example.toml")
        os.environ["MINEBOX_HARDWARE_CONFIG"] = str(ROOT / "config" / "hardware.example.toml")
        os.environ["MINEBOX_RUNTIME_DIR"] = str(ROOT / ".test-runtime")
        Path(os.environ["MINEBOX_RUNTIME_DIR"]).mkdir(parents=True, exist_ok=True)

        import sys

        app_dir = str(ROOT / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)

        from core.minebox_config import clear_config_cache
        from core.state_service import reset_state_service
        from hardware.factory import reset_hardware

        clear_config_cache()
        reset_hardware()
        reset_state_service()

    def test_public_status_contains_no_secrets(self) -> None:
        from core.state_service import get_state_service

        data = get_state_service().public_status()
        self.assertTrue(data.get("ok"))
        self.assertIn("setup", data)
        self.assertIn("minecraft", data)
        self.assertIn("hardware", data)
        self.assertIn("providers", data)
        blob = str(data)
        self.assertNotIn("mineboxsetup", blob)
        self.assertNotIn("MineBoxLocalRcon", blob)
        self.assertNotIn("password_hash", blob)
        self.assertNotIn("session_secret", blob)

    def test_setup_incomplete_reported(self) -> None:
        from core.state_service import get_state_service

        setup = get_state_service().setup_state()
        self.assertIn("first_boot_complete", setup)
        self.assertIn("pending_credential_rotations", setup)
        self.assertIn("incomplete", setup["message"].lower())

    def test_hardware_diag_snapshot(self) -> None:
        from hardware.factory import get_hardware

        snap = get_hardware().diagnostic_snapshot()
        self.assertEqual(snap["profile"], "mock")
        self.assertIn("capabilities", snap)

    def test_http_route_if_fastapi_available(self) -> None:
        try:
            from fastapi.testclient import TestClient
            from api.server import app
        except Exception:
            self.skipTest("fastapi not installed in this environment")
        client = TestClient(app)
        response = client.get("/api/v1/status/foundation")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))


if __name__ == "__main__":
    unittest.main()
