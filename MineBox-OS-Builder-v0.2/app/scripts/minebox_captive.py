#!/usr/bin/python3
"""Hotspot captive portal + HTTP dashboard front-door on port 80.

Phones/PCs open http://192.168.4.1 (port 80). The dashboard listens on 8080
(optionally HTTPS). This server:
  - answers Microsoft/Android/Apple captive probes on port 80 (no DNS hijacks)
  - reverse-proxies everything else to the local dashboard over HTTP so hotspot
    clients get a working UI without self-signed certificate friction
"""
from __future__ import annotations

import http.client
import ssl
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


TLS_ENABLED = Path("/var/lib/minebox/tls/enabled")
DASHBOARD_HOST = "192.168.4.1"
DASHBOARD_PORT = 8080
# When TLS is on, minebox_api_run exposes plain HTTP on loopback :8081 behind
# the dual-protocol gateway on :8080. Prefer that for captive reverse-proxy.
BACKEND_HTTP_PORT = 8081

_REACHABLE_CACHE = {"ok": False, "checked": 0.0}
_REACHABLE_TTL = 2.0


def tls_on() -> bool:
    return TLS_ENABLED.is_file()


def public_dashboard_url() -> str:
    scheme = "https" if tls_on() else "http"
    return f"{scheme}://{DASHBOARD_HOST}:{DASHBOARD_PORT}/"


def backend_host_port() -> tuple[str, int, bool]:
    """Return (host, port, use_tls) for the reverse-proxy target."""
    if tls_on():
        return ("127.0.0.1", BACKEND_HTTP_PORT, False)
    return ("127.0.0.1", DASHBOARD_PORT, False)


def dashboard_reachable() -> bool:
    now = time.monotonic()
    if now - _REACHABLE_CACHE["checked"] < _REACHABLE_TTL:
        return bool(_REACHABLE_CACHE["ok"])

    host, port, use_tls = backend_host_port()
    scheme = "https" if use_tls else "http"
    url = f"{scheme}://{host}:{port}/api/v1/health"
    context = ssl._create_unverified_context() if use_tls else None
    ok = False
    try:
        with urllib.request.urlopen(url, timeout=2, context=context) as response:
            ok = 200 <= int(response.status) < 500
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        if tls_on():
            try:
                url = f"https://127.0.0.1:{DASHBOARD_PORT}/api/v1/health"
                with urllib.request.urlopen(
                    url, timeout=2, context=ssl._create_unverified_context()
                ) as response:
                    ok = 200 <= int(response.status) < 500
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                ok = False
        else:
            ok = False

    _REACHABLE_CACHE["ok"] = ok
    _REACHABLE_CACHE["checked"] = now
    return ok


class CaptiveHandler(BaseHTTPRequestHandler):
    server_version = "MineBoxCaptive/1.2"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _is_captive_probe(self, path: str) -> bool:
        if path.endswith("/connecttest.txt") or path == "/connecttest.txt":
            return True
        if path.endswith("/ncsi.txt") or path == "/ncsi.txt":
            return True
        if "generate_204" in path or path.endswith("/gen_204"):
            return True
        if "hotspot-detect.html" in path or "library/test/success.html" in path:
            return True
        if path in {"/success.txt", "/generate_204"}:
            return True
        return False

    def _answer_probe(self, path: str) -> None:
        if path.endswith("/connecttest.txt") or path == "/connecttest.txt":
            self._send(200, b"Microsoft Connect Test", "text/plain")
            return
        if path.endswith("/ncsi.txt") or path == "/ncsi.txt":
            self._send(200, b"Microsoft NCSI", "text/plain")
            return
        if "generate_204" in path or path.endswith("/gen_204") or path in {
            "/success.txt",
            "/generate_204",
        }:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            return
        if "hotspot-detect.html" in path or "library/test/success.html" in path:
            self._send(
                200,
                b"<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>",
                "text/html",
            )
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def _landing_page(self) -> None:
        http_url = f"http://{DASHBOARD_HOST}/"
        https_url = public_dashboard_url()
        note = ""
        if not dashboard_reachable():
            note = "<p>The dashboard is starting. Wait a few seconds and refresh.</p>"
        https_hint = (
            f"<p>Use <a href='{http_url}'><code>{http_url}</code></a> "
            "(recommended on the setup hotspot).</p>"
        )
        if tls_on():
            https_hint += (
                f"<p>Direct HTTPS: <a href='{https_url}'>{https_url}</a> "
                "(browser will warn on the self-signed cert).</p>"
            )
        else:
            https_hint += (
                "<p>Do not use <code>https://</code> right now — HTTPS is off, "
                "and browsers will show Failed to fetch.</p>"
            )
        body = (
            "<!doctype html><html><head>"
            "<meta http-equiv='refresh' content='3;url=/'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>MineBox Setup</title></head>"
            "<body style='font-family:sans-serif;padding:24px'>"
            "<h1>MineBox</h1>"
            "<p>Waiting for the dashboard…</p>"
            "<p><a href='/'>Retry</a></p>"
            f"{https_hint}{note}"
            "<p>Wi-Fi password is usually <code>mineboxsetup</code> unless you changed it.</p>"
            "</body></html>"
        ).encode()
        self._send(200, body, "text/html; charset=utf-8")

    def _proxy(self) -> None:
        host, port, use_tls = backend_host_port()
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else None

        try:
            if use_tls:
                conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                    host, port, timeout=60, context=ssl._create_unverified_context()
                )
            else:
                conn = http.client.HTTPConnection(host, port, timeout=60)
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower()
                not in {
                    "host",
                    "connection",
                    "content-length",
                    "transfer-encoding",
                    "accept-encoding",
                }
            }
            # Present the public hotspot host to the app (cookies / redirects).
            headers["Host"] = DASHBOARD_HOST
            headers["X-Forwarded-Host"] = DASHBOARD_HOST
            headers["X-Forwarded-Proto"] = "http"
            headers["X-Forwarded-Port"] = "80"
            headers["Connection"] = "close"
            headers["Accept-Encoding"] = "identity"
            conn.request(self.command, self.path, body=body, headers=headers)
            upstream = conn.getresponse()
            payload = upstream.read()
            self.send_response(upstream.status, upstream.reason)
            for key, value in upstream.getheaders():
                if key.lower() in {
                    "transfer-encoding",
                    "connection",
                    "content-length",
                    "content-encoding",
                }:
                    continue
                if key.lower() == "location":
                    value = (
                        value.replace(
                            f"https://{DASHBOARD_HOST}:{DASHBOARD_PORT}",
                            f"http://{DASHBOARD_HOST}",
                        )
                        .replace(
                            f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}",
                            f"http://{DASHBOARD_HOST}",
                        )
                        .replace("https://127.0.0.1:8081", f"http://{DASHBOARD_HOST}")
                        .replace("http://127.0.0.1:8081", f"http://{DASHBOARD_HOST}")
                        .replace("http://127.0.0.1:8080", f"http://{DASHBOARD_HOST}")
                    )
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
            conn.close()
            _REACHABLE_CACHE["ok"] = True
            _REACHABLE_CACHE["checked"] = time.monotonic()
        except (OSError, http.client.HTTPException, ValueError):
            _REACHABLE_CACHE["ok"] = False
            _REACHABLE_CACHE["checked"] = time.monotonic()
            target = f"http://{DASHBOARD_HOST}/"
            body = (
                "<!doctype html><html><body style='font-family:sans-serif;padding:24px'>"
                "<h1>MineBox</h1>"
                "<p>Dashboard is not reachable yet.</p>"
                f"<p>Try <a href='{target}'>{target}</a> "
                f"(not https). Or <a href='{public_dashboard_url()}'>"
                f"{public_dashboard_url()}</a> if HTTPS is enabled.</p>"
                "</body></html>"
            ).encode()
            self._send(502, body, "text/html; charset=utf-8")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        path = (self.path or "/").split("?", 1)[0].lower()
        if self._is_captive_probe(path):
            self._answer_probe(path)
            return
        # Try proxy first; only show landing when backend is clearly down.
        if dashboard_reachable():
            self._proxy()
            return
        self._landing_page()

    def do_POST(self) -> None:  # noqa: N802
        path = (self.path or "/").split("?", 1)[0].lower()
        if self._is_captive_probe(path):
            self._answer_probe(path)
            return
        self._proxy()

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy()

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy()

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._proxy()


class CaptiveServer(ThreadingHTTPServer):
    # Dashboard fans out many parallel fetches; default backlog of 5 drops them.
    request_queue_size = 128
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    server = CaptiveServer(("0.0.0.0", 80), CaptiveHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
