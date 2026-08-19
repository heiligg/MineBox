"""Public Dynamic DNS for internet Minecraft joins.

Friends cannot use minebox.local off the LAN. This publishes
minebox-<slug>.duckdns.org to the current public IP (DuckDNS).

The visible prefix is always "minebox-". The rest of the name is chosen
on the dashboard unless DuckDNS already has it.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services import join_access


STATE_FILE = Path(os.environ.get("MINEBOX_PUBLIC_DNS_FILE", "/var/lib/minebox/public-dns.json"))
DUCKDNS_UPDATE = "https://www.duckdns.org/update"
NAME_PREFIX = "minebox-"
ZONE = "duckdns.org"
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,18}[a-z0-9])?$")
RESERVED = {"local", "www", "api", "setup", "admin", "test"}


class PublicDnsError(Exception):
    pass


def _load_state() -> dict[str, Any]:
    try:
        if STATE_FILE.is_file():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_state(payload: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(STATE_FILE)
    try:
        os.chmod(STATE_FILE, 0o600)
    except OSError:
        pass


def normalize_slug(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = raw.replace("minebox-", "", 1) if raw.startswith("minebox-") else raw
    raw = raw.replace("minebox.", "", 1) if raw.startswith("minebox.") else raw
    raw = raw.split(".", 1)[0]
    raw = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
    if not SLUG_RE.fullmatch(raw) or raw in RESERVED:
        raise PublicDnsError(
            "Pick 3–20 letters or numbers for the part after minebox. "
            "Hyphens are allowed in the middle."
        )
    if len(raw) < 3:
        raise PublicDnsError("The custom name must be at least 3 characters.")
    return raw


def domain_for(slug: str) -> str:
    return f"{NAME_PREFIX}{slug}"


def hostname_for(slug: str) -> str:
    return f"{domain_for(slug)}.{ZONE}"


def status() -> dict[str, Any]:
    state = _load_state()
    slug = str(state.get("slug") or "").strip()
    hostname = hostname_for(slug) if slug else None
    token_set = bool(str(state.get("token") or "").strip())
    return {
        "ok": True,
        "configured": bool(slug and token_set),
        "provider": "duckdns",
        "prefix": NAME_PREFIX.rstrip("-") + ".",
        "slug": slug or None,
        "hostname": hostname,
        "token_set": token_set,
        "last_ip": state.get("last_ip"),
        "last_result": state.get("last_result"),
        "message": state.get("message")
        or (
            "Pick a public name. It will always start with minebox- "
            f"and end with .{ZONE}."
            if not slug
            else None
        ),
        "signup_url": "https://www.duckdns.org",
    }


def _duckdns_update(domain: str, token: str, ip: str) -> tuple[bool, str]:
    query = urllib.parse.urlencode(
        {
            "domains": domain,
            "token": token,
            "ip": ip,
            "verbose": "true",
        }
    )
    url = f"{DUCKDNS_UPDATE}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace").strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"Could not reach DuckDNS: {exc}"
    first = (body.splitlines() or [""])[0].strip().upper()
    if first.startswith("OK"):
        return True, body
    return False, body or "DuckDNS rejected the name or token (KO)."


def claim(*, slug: str, token: str) -> dict[str, Any]:
    clean_slug = normalize_slug(slug)
    clean_token = (token or "").strip() or str(_load_state().get("token") or "").strip()
    if len(clean_token) < 8:
        raise PublicDnsError(
            "Paste your DuckDNS token. Create a free account at duckdns.org, "
            f"add the domain {domain_for(clean_slug)} if it is free, then paste the token."
        )
    ip = join_access.public_ip()
    if not ip:
        raise PublicDnsError(
            "MineBox does not have a public IP yet. Connect to the internet and try again."
        )
    domain = domain_for(clean_slug)
    hostname = hostname_for(clean_slug)
    ok, detail = _duckdns_update(domain, clean_token, ip)
    if not ok:
        raise PublicDnsError(
            f"{hostname} is already taken or is not in your DuckDNS account. "
            f"On duckdns.org add {domain} if it is free, or pick another name. "
            f"({detail[:180]})"
        )
    payload = {
        "slug": clean_slug,
        "token": clean_token,
        "hostname": hostname,
        "last_ip": ip,
        "last_result": "ok",
        "message": (
            f"Public name claimed. Friends can join Minecraft with {hostname}."
        ),
    }
    _save_state(payload)
    return {**status(), "message": payload["message"]}


def refresh() -> dict[str, Any]:
    state = _load_state()
    slug = str(state.get("slug") or "").strip()
    token = str(state.get("token") or "").strip()
    if not slug or not token:
        return status()
    ip = join_access.public_ip()
    if not ip:
        state["last_result"] = "no_public_ip"
        state["message"] = "Skipped DNS update; no public IP."
        _save_state(state)
        return status()
    if ip == state.get("last_ip") and state.get("last_result") == "ok":
        current = status()
        current["skipped"] = True
        return current
    ok, detail = _duckdns_update(domain_for(slug), token, ip)
    state["last_ip"] = ip
    state["last_result"] = "ok" if ok else "error"
    state["message"] = (
        f"Updated {hostname_for(slug)} to {ip}."
        if ok
        else f"DuckDNS update failed: {detail[:180]}"
    )
    _save_state(state)
    return status()


def clear() -> dict[str, Any]:
    state = _load_state()
    token = str(state.get("token") or "").strip()
    _save_state({"token": token} if token else {})
    current = status()
    current["message"] = "Public DNS name cleared on this MineBox."
    return current
