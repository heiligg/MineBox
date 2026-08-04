"""Stable network interface role detection (not wlan0/wlan1 name-only)."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("minebox.network.roles")

ROLE_HOTSPOT = "hotspot"
ROLE_WIFI_UPLINK = "wifi_uplink"
ROLE_ETHERNET_UPLINK = "ethernet_uplink"
ROLE_UNUSED = "unused"


@dataclass
class InterfaceInfo:
    name: str
    mac: str = ""
    sysfs: str = ""
    is_wifi: bool = False
    is_ethernet: bool = False
    is_usb: bool = False
    usb_vendor: str = ""
    usb_product: str = ""
    driver: str = ""

    def identity_key(self) -> str:
        if self.mac:
            return f"mac:{self.mac.lower()}"
        if self.usb_vendor and self.usb_product:
            return f"usb:{self.usb_vendor}:{self.usb_product}:{self.name}"
        return f"sysfs:{self.sysfs or self.name}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RoleAssignment:
    hotspot: str | None = None
    wifi_uplink: str | None = None
    ethernet_uplink: str | None = None
    active_uplink: str | None = None
    local_only: bool = True
    unresolved: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = "auto"
    interfaces: list[InterfaceInfo] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "hotspot": self.hotspot,
            "wifi_uplink": self.wifi_uplink,
            "ethernet_uplink": self.ethernet_uplink,
            "active_uplink": self.active_uplink,
            "local_only": self.local_only,
            "unresolved": list(self.unresolved),
            "warnings": list(self.warnings),
            "source": self.source,
            "interfaces": [i.to_dict() for i in self.interfaces],
        }


def _runtime_dir() -> Path:
    return Path(os.environ.get("MINEBOX_RUNTIME_DIR", "/var/lib/minebox"))


def roles_path() -> Path:
    override = os.environ.get("MINEBOX_NETWORK_ROLES_FILE")
    if override:
        return Path(override)
    return _runtime_dir() / "network_roles.json"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def discover_interfaces(sysfs_root: Path | None = None) -> list[InterfaceInfo]:
    """Inventory interfaces from sysfs (mockable via sysfs_root)."""
    root = sysfs_root or Path("/sys/class/net")
    if not root.is_dir():
        return []

    items: list[InterfaceInfo] = []
    for entry in sorted(root.iterdir()):
        name = entry.name
        if name == "lo":
            continue
        mac = _read_text(entry / "address").lower()
        device = entry / "device"
        is_wifi = (entry / "wireless").is_dir() or (entry / "phy80211").exists()
        # Ethernet-ish: has device symlink and not wifi, not bridge/tun
        is_virtual = name.startswith(("docker", "veth", "br-", "virbr", "tailscale", "ts-"))
        is_ethernet = (not is_wifi) and (not is_virtual) and name.startswith(("eth", "en", "usb"))
        if not is_wifi and not is_ethernet:
            # Broaden ethernet: carrier file without wireless
            if (entry / "type").is_file() and _read_text(entry / "type") == "1" and not is_wifi:
                if not is_virtual:
                    is_ethernet = True

        is_usb = False
        usb_vendor = ""
        usb_product = ""
        driver = ""
        try:
            resolved = device.resolve() if device.exists() else None
            if resolved is not None:
                path_str = str(resolved)
                is_usb = "/usb" in path_str
                vendor_path = resolved / "idVendor"
                product_path = resolved / "idProduct"
                # Walk up for USB ids
                cur = resolved
                for _ in range(6):
                    if (cur / "idVendor").is_file():
                        usb_vendor = _read_text(cur / "idVendor")
                        usb_product = _read_text(cur / "idProduct")
                        is_usb = True
                        break
                    cur = cur.parent
                driver_link = resolved / "driver"
                if driver_link.exists():
                    driver = driver_link.resolve().name
        except OSError:
            pass

        items.append(
            InterfaceInfo(
                name=name,
                mac=mac,
                sysfs=str(entry),
                is_wifi=is_wifi,
                is_ethernet=is_ethernet,
                is_usb=is_usb,
                usb_vendor=usb_vendor,
                usb_product=usb_product,
                driver=driver,
            )
        )
    return items


def load_persisted_roles() -> dict[str, Any]:
    path = roles_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_persisted_roles(assignment: RoleAssignment) -> None:
    path = roles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "hotspot": assignment.hotspot,
        "wifi_uplink": assignment.wifi_uplink,
        "ethernet_uplink": assignment.ethernet_uplink,
        "hotspot_identity": _identity_for(assignment, assignment.hotspot),
        "wifi_uplink_identity": _identity_for(assignment, assignment.wifi_uplink),
        "ethernet_uplink_identity": _identity_for(assignment, assignment.ethernet_uplink),
        "source": assignment.source,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _identity_for(assignment: RoleAssignment, name: str | None) -> str | None:
    if not name:
        return None
    for iface in assignment.interfaces:
        if iface.name == name:
            return iface.identity_key()
    return None


def _config_overrides() -> dict[str, Any]:
    """Read optional network role overrides from MineBox config / env."""
    overrides: dict[str, Any] = {
        "hotspot_role": "prefer_usb_wifi",
        "client_role": "prefer_remaining_wifi_or_ethernet",
        "hotspot_override": os.environ.get("MINEBOX_HOTSPOT_IFACE", "").strip() or None,
        "wifi_uplink_override": os.environ.get("MINEBOX_WIFI_UPLINK_IFACE", "").strip() or None,
        "ethernet_override": os.environ.get("MINEBOX_ETHERNET_IFACE", "").strip() or None,
        "exclude": [
            x.strip()
            for x in os.environ.get("MINEBOX_NETWORK_EXCLUDE", "").split(",")
            if x.strip()
        ],
        "preferred_hotspot_mac": os.environ.get("MINEBOX_HOTSPOT_MAC", "").strip().lower()
        or None,
        "preferred_hotspot_usb": os.environ.get("MINEBOX_HOTSPOT_USB", "").strip().lower()
        or None,
    }
    try:
        from core.minebox_config import get_config

        cfg = get_config()
        overrides["hotspot_role"] = cfg.hotspot_interface_role
        overrides["client_role"] = cfg.client_interface_role
        # Optional keys via raw TOML if present on config object later.
    except Exception:
        pass
    return overrides


def _match_identity(ifaces: list[InterfaceInfo], identity: str | None) -> InterfaceInfo | None:
    if not identity:
        return None
    for iface in ifaces:
        if iface.identity_key() == identity or iface.mac == identity.replace("mac:", ""):
            return iface
        if identity.startswith("usb:") and iface.usb_vendor and iface.usb_product:
            if identity.startswith(f"usb:{iface.usb_vendor}:{iface.usb_product}"):
                return iface
    return None


def resolve_roles(
    interfaces: list[InterfaceInfo] | None = None,
    *,
    persist: bool = True,
    allow_silent_reassign: bool = False,
) -> RoleAssignment:
    """Resolve hotspot / uplink roles using identity signals + config."""
    ifaces = interfaces if interfaces is not None else discover_interfaces()
    overrides = _config_overrides()
    excluded = set(overrides.get("exclude") or [])
    usable = [i for i in ifaces if i.name not in excluded]
    wifi = [i for i in usable if i.is_wifi]
    ethernet = [i for i in usable if i.is_ethernet]

    assignment = RoleAssignment(interfaces=usable)
    persisted = load_persisted_roles()
    warnings: list[str] = []
    unresolved: list[str] = []

    # Manual overrides win.
    if overrides.get("hotspot_override"):
        name = overrides["hotspot_override"]
        if any(i.name == name for i in wifi):
            assignment.hotspot = name
            assignment.source = "manual_override"
        else:
            unresolved.append(f"hotspot_override_missing:{name}")

    if overrides.get("ethernet_override"):
        name = overrides["ethernet_override"]
        if any(i.name == name for i in ethernet):
            assignment.ethernet_uplink = name
        else:
            unresolved.append(f"ethernet_override_missing:{name}")

    if overrides.get("wifi_uplink_override"):
        name = overrides["wifi_uplink_override"]
        if any(i.name == name for i in wifi):
            assignment.wifi_uplink = name
        else:
            unresolved.append(f"wifi_uplink_override_missing:{name}")

    # Preferred MAC / USB for hotspot.
    if assignment.hotspot is None and overrides.get("preferred_hotspot_mac"):
        mac = overrides["preferred_hotspot_mac"]
        for iface in wifi:
            if iface.mac == mac:
                assignment.hotspot = iface.name
                assignment.source = "preferred_mac"
                break

    if assignment.hotspot is None and overrides.get("preferred_hotspot_usb"):
        needle = overrides["preferred_hotspot_usb"]
        for iface in wifi:
            key = f"{iface.usb_vendor}:{iface.usb_product}".lower()
            if needle in key and iface.is_usb:
                assignment.hotspot = iface.name
                assignment.source = "preferred_usb"
                break

    # Restore persisted identity (not bare name) when possible.
    if assignment.hotspot is None:
        match = _match_identity(wifi, persisted.get("hotspot_identity"))
        if match:
            if persisted.get("hotspot") and persisted.get("hotspot") != match.name:
                warnings.append(
                    f"Hotspot interface renamed: {persisted.get('hotspot')} → {match.name}"
                )
            assignment.hotspot = match.name
            assignment.source = "persisted_identity"
        elif persisted.get("hotspot") and not allow_silent_reassign:
            # Stale name — do not silently pick a random adapter.
            if any(i.name == persisted["hotspot"] for i in wifi):
                assignment.hotspot = persisted["hotspot"]
                assignment.source = "persisted_name"
            else:
                unresolved.append("stale_hotspot_assignment")
                warnings.append(
                    "Previous hotspot adapter missing; refusing silent reassignment. "
                    "Set MINEBOX_HOTSPOT_IFACE or clear network_roles.json after confirming."
                )

    # Automatic hotspot selection (never after a stale persisted assignment warning).
    stale_block = "stale_hotspot_assignment" in unresolved and not allow_silent_reassign
    if assignment.hotspot is None and wifi and not stale_block:
        role = str(overrides.get("hotspot_role") or "prefer_usb_wifi")
        if role == "prefer_usb_wifi":
            usb_wifi = [i for i in wifi if i.is_usb]
            assignment.hotspot = (usb_wifi[0] if usb_wifi else wifi[0]).name
        elif role == "prefer_onboard_wifi":
            onboard = [i for i in wifi if not i.is_usb]
            assignment.hotspot = (onboard[0] if onboard else wifi[0]).name
        elif role.startswith("iface:"):
            wanted = role.split(":", 1)[1]
            assignment.hotspot = wanted if any(i.name == wanted for i in wifi) else wifi[0].name
        else:
            onboard = [i for i in wifi if not i.is_usb]
            assignment.hotspot = (onboard[0] if onboard else wifi[0]).name
        assignment.source = "auto"
    elif stale_block and assignment.hotspot is None:
        assignment.source = "stale_blocked"

    # Ethernet uplink.
    if assignment.ethernet_uplink is None and ethernet:
        match = _match_identity(ethernet, persisted.get("ethernet_uplink_identity"))
        assignment.ethernet_uplink = match.name if match else ethernet[0].name

    # Wi-Fi uplink = remaining wifi not used as hotspot.
    if assignment.wifi_uplink is None:
        candidates = [i for i in wifi if i.name != assignment.hotspot]
        match = _match_identity(candidates, persisted.get("wifi_uplink_identity"))
        if match:
            assignment.wifi_uplink = match.name
        elif candidates:
            assignment.wifi_uplink = candidates[0].name

    if not wifi:
        unresolved.append("no_wifi_adapter")
    if assignment.hotspot is None:
        unresolved.append("hotspot_unassigned")

    assignment.unresolved = unresolved
    assignment.warnings = warnings
    assignment.local_only = assignment.active_uplink is None

    if persist and assignment.hotspot:
        try:
            save_persisted_roles(assignment)
        except OSError as exc:
            LOGGER.warning("Could not persist network roles: %s", exc)

    return assignment


def set_active_uplink(assignment: RoleAssignment, uplink: str | None) -> RoleAssignment:
    assignment.active_uplink = uplink
    assignment.local_only = uplink is None
    return assignment


_IFACE_SAFE = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")


def validate_iface_name(name: str | None) -> str | None:
    if not name:
        return None
    if not _IFACE_SAFE.fullmatch(name):
        raise ValueError("Invalid interface name.")
    return name
