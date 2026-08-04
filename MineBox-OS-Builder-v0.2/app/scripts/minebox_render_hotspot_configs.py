#!/usr/bin/env python3
"""Render hostapd/dnsmasq/nft/sysctl/networkd configs from interface roles.

Does not invent GPIO or redesign networking — substitutes the resolved hotspot
iface into known templates. Safe to run multiple times (idempotent).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

def _app_root() -> Path:
    return Path(os.environ.get("MINEBOX_APP_DIR", "/opt/minebox"))


APP_ROOT = _app_root()
TEMPLATE_DIR = APP_ROOT / "services" / "hotspot"


def _resolve_hotspot_iface(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("MINEBOX_HOTSPOT_IFACE", "").strip()
    if env:
        return env
    try:
        root = _app_root()
        sys.path.insert(0, str(root))
        from networking.roles import resolve_roles

        assignment = resolve_roles(persist=True)
        if assignment.hotspot:
            return assignment.hotspot
    except Exception as exc:  # noqa: BLE001
        print(f"role resolve fallback: {exc}", file=sys.stderr)
    return "wlan0"


def _replace_iface(text: str, old: str, new: str) -> str:
    if old == new:
        return text
    # Word-boundary-ish replacements for common config forms.
    patterns = [
        (rf"(?m)^(interface=){re.escape(old)}\s*$", rf"\g<1>{new}"),
        (rf'iifname "{re.escape(old)}"', f'iifname "{new}"'),
        (rf'oifname "{re.escape(old)}"', f'oifname "{new}"'),
        (rf'oifname != "{re.escape(old)}"', f'oifname != "{new}"'),
        (rf'iifname != "{re.escape(old)}"', f'iifname != "{new}"'),
        (rf"\b{re.escape(old)}\b", new),
    ]
    out = text
    for pat, repl in patterns:
        out = re.sub(pat, repl, out)
    return out


def _write(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN write {path} ({len(content)} bytes)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    print(f"wrote {path}")


def render(hotspot_iface: str, *, dry_run: bool = False, write_nft: bool = True) -> dict:
    global APP_ROOT, TEMPLATE_DIR
    APP_ROOT = _app_root()
    TEMPLATE_DIR = APP_ROOT / "services" / "hotspot"
    iface = hotspot_iface
    results: dict = {"hotspot_iface": iface, "files": []}

    # hostapd
    hostapd_src = TEMPLATE_DIR / "hostapd.conf"
    if hostapd_src.is_file():
        text = hostapd_src.read_text(encoding="utf-8")
        text = _replace_iface(text, "wlan0", iface)
        _write(Path("/etc/hostapd/hostapd.conf"), text, dry_run)
        results["files"].append("/etc/hostapd/hostapd.conf")

    # dnsmasq
    dnsmasq_src = TEMPLATE_DIR / "dnsmasq-minebox.conf"
    if dnsmasq_src.is_file():
        text = dnsmasq_src.read_text(encoding="utf-8")
        text = _replace_iface(text, "wlan0", iface)
        dest = Path("/etc/dnsmasq.d/minebox.conf")
        # Preserve legacy filename if present
        legacy = Path("/etc/dnsmasq.d/dnsmasq-minebox.conf")
        if legacy.is_file() and not dest.is_file():
            dest = legacy
        _write(dest, text, dry_run)
        results["files"].append(str(dest))

    # systemd-networkd
    network_text = f"""[Match]
Name={iface}

[Network]
Address=192.168.4.1/24
DHCP=no
IPForward=yes
ConfigureWithoutCarrier=yes
IgnoreCarrierLoss=yes
LinkLocalAddressing=no
IPv6AcceptRA=no
"""
    _write(Path("/etc/systemd/network/20-minebox-hotspot.network"), network_text, dry_run)
    results["files"].append("/etc/systemd/network/20-minebox-hotspot.network")
    # Remove stale wlan0-only unit name if iface changed
    stale = Path("/etc/systemd/network/20-minebox-wlan0.network")
    if iface != "wlan0" and stale.is_file() and not dry_run:
        stale.unlink(missing_ok=True)

    # NM unmanaged
    nm_text = f"""[keyfile]
unmanaged-devices=interface-name:{iface}
"""
    _write(Path("/etc/NetworkManager/conf.d/10-minebox-unmanaged.conf"), nm_text, dry_run)
    results["files"].append("/etc/NetworkManager/conf.d/10-minebox-unmanaged.conf")

    # sysctl
    sysctl = f"""net.ipv4.ip_forward=1
net.ipv6.conf.{iface}.disable_ipv6=1
net.ipv4.conf.{iface}.rp_filter=0
"""
    _write(Path("/etc/sysctl.d/90-minebox-router.conf"), sysctl, dry_run)
    results["files"].append("/etc/sysctl.d/90-minebox-router.conf")

    # hostapd drop-in power save off
    dropin = f"""[Unit]
After=systemd-networkd.service
Wants=systemd-networkd.service

[Service]
ExecStartPost=/bin/sh -c '/sbin/iwconfig {iface} power off 2>/dev/null || /usr/sbin/iw dev {iface} set power_save off 2>/dev/null || true'
Restart=on-failure
RestartSec=3
"""
    if not dry_run:
        Path("/etc/systemd/system/hostapd.service.d").mkdir(parents=True, exist_ok=True)
    _write(Path("/etc/systemd/system/hostapd.service.d/minebox.conf"), dropin, dry_run)
    results["files"].append("/etc/systemd/system/hostapd.service.d/minebox.conf")

    # nftables from generator
    if write_nft:
        try:
            sys.path.insert(0, str(APP_ROOT))
            from networking.firewall import (  # type: ignore
                build_policy_for_roles,
                internet_sharing_enabled,
                write_nftables_file,
            )

            policy = build_policy_for_roles(iface, has_uplink=internet_sharing_enabled())
            if policy["validation"]["ok"]:
                if dry_run:
                    print(f"DRY-RUN nftables ({len(policy['ruleset'])} bytes)")
                else:
                    write_nftables_file(policy["ruleset"], Path("/etc/nftables.conf"))
                    print("wrote /etc/nftables.conf")
                results["files"].append("/etc/nftables.conf")
            else:
                results["nft_errors"] = policy["validation"]["errors"]
        except Exception as exc:  # noqa: BLE001
            # Fall back to template substitution
            nft_src = TEMPLATE_DIR / "minebox-hotspot.nft"
            if nft_src.is_file():
                text = _replace_iface(nft_src.read_text(encoding="utf-8"), "wlan0", iface)
                _write(Path("/etc/nftables.conf"), text, dry_run)
                results["files"].append("/etc/nftables.conf")
                results["nft_fallback"] = str(exc)

    marker = Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox")) / "hotspot_iface"
    if not dry_run:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(iface + "\n", encoding="utf-8")
    results["marker"] = str(marker)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iface", default=None, help="Force hotspot interface name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-nft", action="store_true")
    args = parser.parse_args(argv)
    iface = _resolve_hotspot_iface(args.iface)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", iface):
        print(f"invalid iface: {iface}", file=sys.stderr)
        return 2
    result = render(iface, dry_run=args.dry_run, write_nft=not args.skip_nft)
    print(f"hotspot_iface={result['hotspot_iface']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
