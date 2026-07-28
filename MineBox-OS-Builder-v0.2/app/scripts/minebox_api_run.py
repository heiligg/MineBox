#!/usr/bin/python3
"""Start the MineBox API with optional HTTPS (self-signed TLS).

When TLS is enabled, uvicorn speaks plain HTTP on 127.0.0.1:8081 and a small
gateway on 0.0.0.0:8080 accepts both:
  - HTTP  -> 302 redirect to https://<host>:8080/...
  - HTTPS -> TLS terminate, then TCP-proxy to the backend

That way http://192.168.4.1:8080 no longer returns an empty reply when TLS is on.
"""
from __future__ import annotations

import os
import select
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path


TLS_DIR = Path("/var/lib/minebox/tls")
CERT_FILE = TLS_DIR / "cert.pem"
KEY_FILE = TLS_DIR / "key.pem"
ENABLED_FLAG = TLS_DIR / "enabled"

PUBLIC_HOST = "0.0.0.0"
PUBLIC_PORT = 8080
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8081


def _tls_enabled() -> bool:
    return ENABLED_FLAG.is_file() and CERT_FILE.is_file() and KEY_FILE.is_file()


def _uvicorn_cmd(*, host: str, port: int, with_tls: bool) -> list[str]:
    args = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.server:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if with_tls:
        args.extend(
            [
                "--ssl-certfile",
                str(CERT_FILE),
                "--ssl-keyfile",
                str(KEY_FILE),
            ]
        )
    return args


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 60)
            if not r:
                break
            for src, dst in ((a, b), (b, a)):
                if src not in r:
                    continue
                data = src.recv(65536)
                if not data:
                    return
                dst.sendall(data)
    except OSError:
        return
    finally:
        for sock in (a, b):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


def _read_http_head(conn: socket.socket) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 65536:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def _http_redirect(conn: socket.socket, raw: bytes) -> None:
    head = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace")
    lines = head.split("\r\n")
    request = lines[0] if lines else "GET / HTTP/1.1"
    parts = request.split(" ")
    path = parts[1] if len(parts) >= 2 else "/"
    host = "192.168.4.1:8080"
    for line in lines[1:]:
        if line.lower().startswith("host:"):
            host = line.split(":", 1)[1].strip() or host
            break
    # Preserve hostname but force https on the public dashboard port.
    hostname = host.split(":")[0] or "192.168.4.1"
    location = f"https://{hostname}:{PUBLIC_PORT}{path}"
    body = (
        "<!doctype html><html><body>"
        f"<a href='{location}'>Continue to MineBox dashboard</a>"
        "</body></html>"
    ).encode()
    response = (
        "HTTP/1.1 302 Found\r\n"
        f"Location: {location}\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode() + body
    try:
        conn.sendall(response)
    except OSError:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _https_proxy(conn: socket.socket, ctx: ssl.SSLContext) -> None:
    try:
        tls_conn = ctx.wrap_socket(conn, server_side=True)
    except ssl.SSLError:
        try:
            conn.close()
        except OSError:
            pass
        return
    try:
        backend = socket.create_connection((BACKEND_HOST, BACKEND_PORT), timeout=5)
    except OSError:
        try:
            tls_conn.close()
        except OSError:
            pass
        return
    _pipe(tls_conn, backend)


def _handle_client(conn: socket.socket, ctx: ssl.SSLContext) -> None:
    try:
        conn.settimeout(15)
        first = conn.recv(1, socket.MSG_PEEK)
        if not first:
            conn.close()
            return
        if first[0] == 0x16:
            _https_proxy(conn, ctx)
            return
        raw = _read_http_head(conn)
        if not raw:
            conn.close()
            return
        _http_redirect(conn, raw)
    except OSError:
        try:
            conn.close()
        except OSError:
            pass


def _wait_backend(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((BACKEND_HOST, BACKEND_PORT), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _run_tls_gateway() -> int:
    os.environ["MINEBOX_TLS"] = "1"
    backend = subprocess.Popen(
        _uvicorn_cmd(host=BACKEND_HOST, port=BACKEND_PORT, with_tls=False),
        cwd="/opt/minebox",
        env={**os.environ, "PYTHONPATH": "/opt/minebox"},
    )
    try:
        if not _wait_backend():
            print("backend failed to start on 127.0.0.1:8081", file=sys.stderr)
            backend.terminate()
            return 1

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((PUBLIC_HOST, PUBLIC_PORT))
        server.listen(128)
        print(f"MineBox TLS gateway on {PUBLIC_HOST}:{PUBLIC_PORT} -> {BACKEND_HOST}:{BACKEND_PORT}")

        while True:
            if backend.poll() is not None:
                print("uvicorn backend exited", file=sys.stderr)
                return backend.returncode or 1
            try:
                server.settimeout(1.0)
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            thread = threading.Thread(
                target=_handle_client, args=(conn, ctx), daemon=True
            )
            thread.start()
    finally:
        if backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                backend.kill()
    return 0


def main() -> int:
    os.environ.setdefault("PYTHONPATH", "/opt/minebox")
    os.chdir("/opt/minebox")

    if _tls_enabled():
        return _run_tls_gateway()

    os.environ.pop("MINEBOX_TLS", None)
    args = _uvicorn_cmd(host=PUBLIC_HOST, port=PUBLIC_PORT, with_tls=False)
    os.execv(sys.executable, args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
