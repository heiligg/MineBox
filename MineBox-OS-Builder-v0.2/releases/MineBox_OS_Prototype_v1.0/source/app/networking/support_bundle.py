"""Redacted network diagnostics for support bundles."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.secrets_store import redact_secrets
from networking import firewall, recovery, roles, state


SENSITIVE_KEYS = {
    "password",
    "psk",
    "passphrase",
    "auth_key",
    "authkey",
    "auth-key",
    "secret",
    "token",
    "privatekey",
    "private_key",
}


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            lowered = str(key).lower()
            if any(s in lowered for s in SENSITIVE_KEYS):
                out[key] = "[REDACTED]"
            else:
                out[key] = _scrub(value)
        return out
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    if isinstance(obj, str):
        return redact_secrets(obj)
    return obj


def _safe_read(path: Path, limit: int = 8000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return redact_secrets(text[:limit])
    except OSError as exc:
        return f"[unavailable: {exc}]"


def build_network_support_bundle() -> dict[str, Any]:
    assignment = roles.resolve_roles(persist=False)
    snap = state.snapshot(authenticated=False, include_legacy=False)
    # Regenerate policy text for summary (do not include full secrets).
    policy = firewall.build_policy_for_roles(
        assignment.hotspot, has_uplink=bool(snap.get("active_uplink"))
    )
    rules_summary = {
        "validation": policy["validation"],
        "internet_sharing_active": policy["internet_sharing_active"],
        "hotspot_iface": policy["hotspot_iface"],
        "ruleset_sha_prefix": str(hash(policy["ruleset"]) % 10_000_000),
        "ruleset_lines": len(policy["ruleset"].splitlines()),
        # Include a redacted truncated ruleset for support (no secrets there).
        "ruleset_excerpt": "\n".join(policy["ruleset"].splitlines()[:80]),
    }

    remote = snap.get("remote_access") or {}
    # Strip node identity for unauthenticated bundle section.
    remote_safe = {
        "state": remote.get("state"),
        "enabled": remote.get("enabled"),
        "provider": remote.get("provider"),
        "connected": remote.get("connected"),
        "expose_dashboard": remote.get("expose_dashboard"),
        "expose_minecraft": remote.get("expose_minecraft"),
        "detail": redact_secrets(str(remote.get("detail") or "")),
    }

    bundle = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_inventory": [i.to_dict() for i in assignment.interfaces],
        "role_assignment": assignment.to_public_dict(),
        "network_state": _scrub(snap),
        "hostapd_active_hint": snap.get("hotspot", {}).get("hostapd"),
        "dnsmasq_active_hint": snap.get("hotspot", {}).get("dnsmasq"),
        "nftables_summary": rules_summary,
        "connectivity_check": snap.get("internet"),
        "tailscale": remote_safe,
        "recovery": recovery.status(),
        "recent_errors": [
            recovery.status().get("last_error"),
            *(assignment.warnings or []),
            *(assignment.unresolved or []),
        ],
        "config_snippets": {
            "hostapd_conf": _safe_read(Path("/etc/hostapd/hostapd.conf")),
            "dnsmasq_conf": _safe_read(Path("/etc/dnsmasq.d/minebox.conf")),
        },
    }
    return _scrub(bundle)


def write_support_bundle(directory: Path | None = None) -> Path:
    root = directory or Path(
        os.environ.get("MINEBOX_SUPPORT_DIR", "/var/lib/minebox/support")
    )
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"network-support-{stamp}.json"
    path.write_text(json.dumps(build_network_support_bundle(), indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
