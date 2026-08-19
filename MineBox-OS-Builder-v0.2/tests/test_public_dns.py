"""Public DuckDNS hostname claim tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from services import public_dns
from services.public_dns import PublicDnsError


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class PublicDnsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.state = Path(self._temp.name) / "public-dns.json"
        self._state_patch = mock.patch.object(public_dns, "STATE_FILE", self.state)
        self._state_patch.start()

    def tearDown(self) -> None:
        self._state_patch.stop()
        self._temp.cleanup()

    def test_normalize_slug_strips_prefix(self) -> None:
        self.assertEqual(public_dns.normalize_slug("Claire"), "claire")
        self.assertEqual(public_dns.normalize_slug("minebox-claire"), "claire")
        self.assertEqual(public_dns.normalize_slug("minebox.claire.duckdns.org"), "claire")
        self.assertEqual(
            public_dns.hostname_for("claire"),
            "minebox-claire.duckdns.org",
        )

    def test_rejects_short_or_reserved_slug(self) -> None:
        with self.assertRaises(PublicDnsError):
            public_dns.normalize_slug("ab")
        with self.assertRaises(PublicDnsError):
            public_dns.normalize_slug("local")

    def test_claim_writes_hostname_on_ok(self) -> None:
        with mock.patch.object(
            public_dns.join_access, "public_ip", return_value="205.237.131.135"
        ), mock.patch(
            "services.public_dns.urllib.request.urlopen",
            return_value=_FakeResponse("OK\n205.237.131.135"),
        ):
            result = public_dns.claim(slug="claire", token="duckdns-token-123")
        self.assertTrue(result["configured"])
        self.assertEqual(result["hostname"], "minebox-claire.duckdns.org")
        saved = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(saved["last_ip"], "205.237.131.135")
        self.assertNotIn("duckdns-token-123", json.dumps(result))

    def test_claim_rejects_taken_name(self) -> None:
        with mock.patch.object(
            public_dns.join_access, "public_ip", return_value="8.8.8.8"
        ), mock.patch(
            "services.public_dns.urllib.request.urlopen",
            return_value=_FakeResponse("KO"),
        ):
            with self.assertRaises(PublicDnsError) as raised:
                public_dns.claim(slug="takenname", token="duckdns-token-123")
        self.assertIn("already taken", str(raised.exception))
        self.assertFalse(self.state.is_file())

    def test_refresh_skips_when_ip_unchanged(self) -> None:
        self.state.write_text(
            json.dumps(
                {
                    "slug": "claire",
                    "token": "duckdns-token-123",
                    "hostname": "minebox-claire.duckdns.org",
                    "last_ip": "1.2.3.4",
                    "last_result": "ok",
                }
            ),
            encoding="utf-8",
        )
        with mock.patch.object(
            public_dns.join_access, "public_ip", return_value="1.2.3.4"
        ), mock.patch(
            "services.public_dns.urllib.request.urlopen"
        ) as opener:
            result = public_dns.refresh()
        opener.assert_not_called()
        self.assertTrue(result.get("skipped"))


if __name__ == "__main__":
    unittest.main()
