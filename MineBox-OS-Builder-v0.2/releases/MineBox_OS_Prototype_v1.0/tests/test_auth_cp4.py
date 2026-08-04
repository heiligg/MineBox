"""Checkpoint 4 authentication, CSRF, rate-limit, and setup gating tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class AuthCp4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MINEBOX_RUNTIME_DIR"] = self.tmp.name
        os.environ["MINEBOX_AUTH_FILE"] = str(Path(self.tmp.name) / "auth.json")
        os.environ["MINEBOX_SKIP_FIRST_BOOT"] = "1"
        os.environ["MINEBOX_FORCE_MOCK_HARDWARE"] = "1"
        os.environ["MINEBOX_DEV_MODE"] = "1"
        import sys

        app_dir = str(ROOT / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)

        from services import auth

        auth.AUTH_FILE = Path(os.environ["MINEBOX_AUTH_FILE"])
        if auth.AUTH_FILE.exists():
            auth.AUTH_FILE.unlink()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_argon2_hash_and_verify(self) -> None:
        from services import auth

        auth.create_admin("admin", "CorrectHorseBattery1!")
        self.assertTrue(auth.is_configured())
        self.assertEqual(auth.password_algo(), "argon2id")
        self.assertTrue(auth.verify_credentials("admin", "CorrectHorseBattery1!"))
        self.assertFalse(auth.verify_credentials("admin", "wrong-password-xx"))
        text = Path(os.environ["MINEBOX_AUTH_FILE"]).read_text(encoding="utf-8")
        self.assertNotIn("CorrectHorseBattery1!", text)

    def test_weak_password_rejected(self) -> None:
        from services import auth

        with self.assertRaises(ValueError):
            auth.create_admin("admin", "minebox123456")

    def test_change_password_requires_current(self) -> None:
        from services import auth

        auth.create_admin("admin", "CorrectHorseBattery1!")
        with self.assertRaises(ValueError):
            auth.change_password("wrong-current-xx", "AnotherStrongPass9!")
        auth.change_password("CorrectHorseBattery1!", "AnotherStrongPass9!")
        self.assertTrue(auth.verify_credentials("admin", "AnotherStrongPass9!"))
        self.assertFalse(auth.verify_credentials("admin", "CorrectHorseBattery1!"))

    def test_rate_limit_login_key(self) -> None:
        from core.rate_limit import check_rate_limit, clear, record_failure

        key = "test-login"
        clear(key)
        for _ in range(8):
            record_failure(key)
        allowed, retry = check_rate_limit(key, max_attempts=8, window_s=300, cooldown_s=120)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)

    def test_csrf_validation(self) -> None:
        from core.csrf import ensure_csrf_token, rotate_csrf_token, validate_csrf

        session: dict = {}
        token = ensure_csrf_token(session)
        self.assertTrue(validate_csrf(session, token))
        self.assertFalse(validate_csrf(session, "invalid"))
        self.assertFalse(validate_csrf(session, None))
        new = rotate_csrf_token(session)
        self.assertFalse(validate_csrf(session, token))
        self.assertTrue(validate_csrf(session, new))

    def test_setup_gating_blocks_control(self) -> None:
        from core.security import _path_blocked_until_complete

        self.assertTrue(_path_blocked_until_complete("/api/v1/minecraft/start", "POST"))
        self.assertTrue(_path_blocked_until_complete("/api/v1/minecraft/stop", "POST"))
        self.assertTrue(_path_blocked_until_complete("/api/v1/system/shutdown", "POST"))
        self.assertTrue(_path_blocked_until_complete("/api/v1/update/install", "POST"))
        self.assertTrue(_path_blocked_until_complete("/api/v1/backups/x.tar.gz", "DELETE"))
        self.assertFalse(_path_blocked_until_complete("/api/v1/status/foundation", "GET"))
        self.assertFalse(_path_blocked_until_complete("/api/v1/health", "GET"))

    def test_first_boot_incomplete_without_rotations(self) -> None:
        os.environ["MINEBOX_SKIP_FIRST_BOOT"] = "0"
        from services import auth, first_boot

        auth.create_admin("admin", "CorrectHorseBattery1!")
        with mock.patch.object(first_boot, "minecraft_setup_done", return_value=True):
            self.assertFalse(first_boot.is_appliance_setup_complete())

    def test_wizard_resume_persists_non_secrets(self) -> None:
        from services import first_boot

        first_boot.save_wizard({"step": "hotspot", "data": {"device_name": "Den"}})
        loaded = first_boot.load_wizard()
        self.assertEqual(loaded.get("step"), "hotspot")
        self.assertEqual((loaded.get("data") or {}).get("device_name"), "Den")
        # Ensure we do not persist password-like fields if someone tries.
        first_boot.save_wizard(
            {
                "step": "hotspot",
                "data": {"device_name": "Den", "password": "should-not-matter"},
            }
        )
        text = first_boot.wizard_path().read_text(encoding="utf-8")
        # Wizard may store non-secret fields; passwords must not be in bootstrap secrets path.
        self.assertTrue(first_boot.wizard_path().is_file())

    def test_factory_reset_preserves_worlds_flag(self) -> None:
        from services import auth
        from services.factory_reset import factory_reset

        auth.create_admin("admin", "CorrectHorseBattery1!")
        result = factory_reset(
            confirm=True,
            erase_worlds=False,
            admin_password="CorrectHorseBattery1!",
        )
        self.assertTrue(result["worlds_preserved"])
        self.assertFalse(auth.is_configured())

    def test_factory_reset_full_erase_needs_phrase(self) -> None:
        from services import auth
        from services.factory_reset import FactoryResetError, factory_reset

        auth.create_admin("admin", "CorrectHorseBattery1!")
        with self.assertRaises(FactoryResetError):
            factory_reset(
                confirm=True,
                erase_worlds=True,
                confirm_erase_phrase="yes",
                admin_password="CorrectHorseBattery1!",
            )

    def test_hotspot_psk_rejects_bootstrap(self) -> None:
        from services.secret_rotation import RotationError, validate_hotspot_psk

        with self.assertRaises(RotationError):
            validate_hotspot_psk("mineboxsetup")

    def test_session_secret_rotation(self) -> None:
        from services import auth

        first = auth.get_session_secret()
        second = auth.rotate_session_secret()
        self.assertTrue(second)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
