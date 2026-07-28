#!/usr/bin/python3
"""Hotspot captive portal + dashboard redirect on port 80.

Phones and PCs often drop Wi-Fi networks that fail connectivity checks, and
users open http://192.168.4.1 (port 80) while the dashboard listens on 8080
(optionally HTTPS). This tiny server:
  - answers Microsoft/Android/Apple captive probes
  - redirects browsers to the MineBox dashboard
"""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


TLS_ENABLED = Path("/var/lib/minebox/tls/enabled")
DASHBOARD_HOST = "192.168.4.1"
DASHBOARD_PORT = 8080


def dashboard_url() -> str:
    scheme = "https" if TLS_ENABLED.is_file() else "http"
    return f"{scheme}://{DASHBOARD_HOST}:{DASHBOARD_PORT}/"


def dashboard_reachable() -> bool:
    url = dashboard_url().rstrip("/") + "/api/v1/health"
    context = None
    if url.startswith("https://"):
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(url, timeout=2, context=context) as response:
            return 200 <= int(response.status) < 500
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


class CaptiveHandler(BaseHTTPRequestHandler):
    server_version = "MineBoxCaptive/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Keep journal noise low; hostapd/dnsmasq already show client activity.
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        body = (
            f"<!doctype html><html><head><meta http-equiv='refresh' content='0;url={location}'>"
            f"<title>MineBox</title></head><body>"
            f"<p>Open the MineBox dashboard: "
            f"<a href='{location}'>{location}</a></p></body></html>"
        ).encode()
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        path = (self.path or "/").split("?", 1)[0].lower()

        # Microsoft NCSI / Windows connectivity check
        if path.endswith("/connecttest.txt") or path == "/connecttest.txt":
            self._send(200, b"Microsoft Connect Test", "text/plain")
            return
        if path.endswith("/ncsi.txt") or path == "/ncsi.txt":
            self._send(200, b"Microsoft NCSI", "text/plain")
            return
        if "generate_204" in path or path.endswith("/gen_204"):
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if "hotspot-detect.html" in path or "library/test/success.html" in path:
            self._send(200, b"<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>", "text/html")
            return
        if path in {"/success.txt", "/generate_204"}:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        target = dashboard_url()
        note = ""
        if not dashboard_reachable():
            note = (
                "<p>The dashboard is starting. Wait a few seconds and refresh.</p>"
            )
        body = (
            "<!doctype html><html><head>"
            f"<meta http-equiv='refresh' content='1;url={target}'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>MineBox Setup</title></head><body style='font-family:sans-serif;padding:24px'>"
            "<h1>MineBox</h1>"
            f"<p>Continue to the dashboard:</p>"
            f"<p><a href='{target}'>{target}</a></p>"
            f"{note}"
            "<p>Password for this Wi-Fi is usually <code>mineboxsetup</code> "
            "unless you changed it.</p>"
            "</body></html>"
        ).encode()
        if path in {"/", "/index.html", "/hotspot", "/generate_204"}:
            self._send(200, body, "text/html; charset=utf-8")
            return
        self._redirect(target)

    def do_POST(self) -> None:  # noqa: N802
        self.do_GET()


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", 80), CaptiveHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
