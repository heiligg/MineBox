"""Typed, validated MineBox configuration (non-secret + hardware profile)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping


class ConfigError(Exception):
    """Readable configuration validation failure."""


def _repo_config_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "config"


def default_search_paths() -> list[Path]:
    """Ordered search paths for minebox.toml."""
    env = os.environ.get("MINEBOX_CONFIG")
    paths: list[Path] = []
    if env:
        paths.append(Path(env).expanduser())
    config_dir = Path(os.environ.get("MINEBOX_CONFIG_DIR", "/etc/minebox"))
    paths.append(config_dir / "minebox.toml")
    paths.append(_repo_config_dir() / "minebox.example.toml")
    return paths


def default_hardware_search_paths(profile_file: str | None = None) -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("MINEBOX_HARDWARE_CONFIG")
    if env:
        paths.append(Path(env).expanduser())
    if profile_file:
        paths.append(Path(profile_file).expanduser())
    config_dir = Path(os.environ.get("MINEBOX_CONFIG_DIR", "/etc/minebox"))
    paths.append(config_dir / "hardware.toml")
    paths.append(_repo_config_dir() / "hardware.example.toml")
    return paths


def _as_dict(section: Any, name: str) -> dict[str, Any]:
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ConfigError(f"[{name}] must be a table.")
    return section


def _require_str(data: Mapping[str, Any], key: str, section: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"[{section}] {key} must be a non-empty string.")
    return value.strip()


def _optional_str(data: Mapping[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string.")
    return value.strip()


def _require_int(data: Mapping[str, Any], key: str, section: str, *, min_v: int, max_v: int) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"[{section}] {key} must be an integer.")
    if not (min_v <= value <= max_v):
        raise ConfigError(f"[{section}] {key} must be between {min_v} and {max_v}.")
    return value


def _optional_int(data: Mapping[str, Any], key: str, default: int, *, min_v: int, max_v: int) -> int:
    if key not in data:
        return default
    return _require_int(data, key, key, min_v=min_v, max_v=max_v)


def _optional_float(data: Mapping[str, Any], key: str, default: float) -> float:
    if key not in data or data[key] is None:
        return default
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number.")
    return float(value)


def _optional_bool(data: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false.")
    return value


def _str_list(data: Mapping[str, Any], key: str, default: list[str]) -> list[str]:
    if key not in data:
        return list(default)
    value = data[key]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key} must be a list of strings.")
    return [v.strip().lower() for v in value if v.strip()]


@dataclass(frozen=True)
class ButtonConfig:
    gpio_bcm: int
    physical_pin: int | None
    short_action: str
    long_action: str
    verification: str = "UNVERIFIED_AGAINST_PCB"


@dataclass(frozen=True)
class HardwareConfig:
    profile_name: str
    verification: str
    active_level: str
    pull: str
    debounce_ms: int
    long_press_ms: int
    lockout_ms: int
    poll_ms: int
    left_button: ButtonConfig
    right_button: ButtonConfig
    encoder_enabled: bool
    encoder_status: str
    encoder_gpio_a: int | None
    encoder_gpio_b: int | None
    encoder_gpio_button: int | None
    left_led_status: str
    right_led_status: str
    left_led_gpio: int | None
    right_led_gpio: int | None
    fan_mode: str
    fan_status: str
    fan_gpio: int | None
    fan_off_below_c: float
    fan_on_above_c: float
    fan_warning_c: float
    fan_critical_c: float
    shutdown_method: str
    reboot_method: str


@dataclass(frozen=True)
class MineBoxConfig:
    device_name: str
    hostname: str
    api_bind: str
    api_port: int
    dashboard_bind: str
    dashboard_port: int
    minecraft_data_path: str
    java_path: str
    default_memory_gb: int
    service_name: str
    supported_providers: list[str]
    experimental_providers: list[str]
    hotspot_ssid: str
    hotspot_subnet: str
    hotspot_address: str
    hotspot_interface_role: str
    client_interface_role: str
    internet_sharing: bool
    display_mode: str
    display_width: int
    display_height: int
    display_fallback: str
    hardware_profile: str
    hardware_profile_file: str
    backup_directory: str
    backup_retention_count: int
    preserve_last_backup: bool
    update_channel: str
    logging_level: str
    logging_directory: str
    runtime_state: str
    config_dir: str
    secrets_file: str
    hardware: HardwareConfig = field(repr=False)
    source_path: str = ""
    hardware_source_path: str = ""


def _parse_button(section: Mapping[str, Any], name: str, defaults: Mapping[str, Any]) -> ButtonConfig:
    data = {**defaults, **dict(section)}
    gpio = data.get("gpio_bcm")
    if not isinstance(gpio, int) or isinstance(gpio, bool) or not (0 <= gpio <= 27):
        raise ConfigError(f"[buttons.{name}] gpio_bcm must be an integer BCM pin 0–27.")
    physical = data.get("physical_pin")
    if physical is not None and (not isinstance(physical, int) or isinstance(physical, bool)):
        raise ConfigError(f"[buttons.{name}] physical_pin must be an integer or omitted.")
    short_action = _optional_str(data, "short_action", "nav_previous" if name == "left" else "nav_next")
    long_action = _optional_str(data, "long_action", "back" if name == "left" else "confirm")
    return ButtonConfig(
        gpio_bcm=gpio,
        physical_pin=physical if isinstance(physical, int) else None,
        short_action=short_action,
        long_action=long_action,
        verification=_optional_str(data, "verification", "UNVERIFIED_AGAINST_PCB"),
    )


def _optional_gpio(data: Mapping[str, Any], key: str) -> int | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool) or not (0 <= value <= 27):
        raise ConfigError(f"{key} must be a BCM GPIO integer 0–27 or omitted.")
    return value


def parse_hardware(data: Mapping[str, Any], *, source: str = "") -> HardwareConfig:
    profile = _as_dict(data.get("profile"), "profile")
    buttons = _as_dict(data.get("buttons"), "buttons")
    left = _as_dict(buttons.get("left"), "buttons.left")
    right = _as_dict(buttons.get("right"), "buttons.right")
    encoder = _as_dict(data.get("encoder"), "encoder")
    leds = _as_dict(data.get("leds"), "leds")
    fan = _as_dict(data.get("fan"), "fan")
    power = _as_dict(data.get("power"), "power")

    profile_name = _optional_str(profile, "name", "raspberry_pi5").lower()
    if profile_name not in {"raspberry_pi5", "mock", "cm5"}:
        raise ConfigError(
            f"[profile] name must be raspberry_pi5, mock, or cm5 (got {profile_name!r})."
        )

    active_level = _optional_str(buttons, "active_level", "active_low").lower()
    if active_level not in {"active_low", "active_high"}:
        raise ConfigError("[buttons] active_level must be active_low or active_high.")

    pull = _optional_str(buttons, "pull", "up").lower()
    if pull not in {"up", "down", "none"}:
        raise ConfigError("[buttons] pull must be up, down, or none.")

    debounce_ms = _optional_int(buttons, "debounce_ms", 40, min_v=0, max_v=2000)
    long_press_ms = _optional_int(buttons, "long_press_ms", 450, min_v=50, max_v=5000)
    lockout_ms = _optional_int(buttons, "lockout_ms", 150, min_v=0, max_v=2000)
    poll_ms = _optional_int(buttons, "poll_ms", 5, min_v=1, max_v=100)

    left_defaults = {"gpio_bcm": 23, "physical_pin": 16, "short_action": "nav_previous", "long_action": "back"}
    right_defaults = {"gpio_bcm": 17, "physical_pin": 11, "short_action": "nav_next", "long_action": "confirm"}

    left_btn = _parse_button(left or left_defaults, "left", left_defaults)
    right_btn = _parse_button(right or right_defaults, "right", right_defaults)

    encoder_status = _optional_str(encoder, "status", "NOT_CONFIGURED").upper()
    left_led_status = _optional_str(leds, "left_status", "NOT_CONFIGURED").upper()
    right_led_status = _optional_str(leds, "right_status", "NOT_CONFIGURED").upper()
    fan_status = _optional_str(fan, "status", "NOT_CONFIGURED").upper()
    fan_mode = _optional_str(fan, "mode", "platform").lower()
    if fan_mode not in {"platform", "gpio", "pwm", "disabled"}:
        raise ConfigError("[fan] mode must be platform, gpio, pwm, or disabled.")

    # Refuse invented encoder/LED/fan pins when status says not configured.
    enc_a = _optional_gpio(encoder, "gpio_a")
    enc_b = _optional_gpio(encoder, "gpio_b")
    enc_btn = _optional_gpio(encoder, "gpio_button")
    if encoder_status in {"NOT_CONFIGURED", "UNSUPPORTED"} and any(v is not None for v in (enc_a, enc_b, enc_btn)):
        raise ConfigError(
            "[encoder] pins are set but status is NOT_CONFIGURED/UNSUPPORTED. "
            "Set status only after PCB verification, or remove pin values."
        )

    left_led = _optional_gpio(leds, "left_gpio_bcm")
    right_led = _optional_gpio(leds, "right_gpio_bcm")
    if left_led_status in {"NOT_CONFIGURED", "UNSUPPORTED"} and left_led is not None:
        raise ConfigError("[leds] left_gpio_bcm set while left_status is NOT_CONFIGURED.")
    if right_led_status in {"NOT_CONFIGURED", "UNSUPPORTED"} and right_led is not None:
        raise ConfigError("[leds] right_gpio_bcm set while right_status is NOT_CONFIGURED.")

    fan_gpio = _optional_gpio(fan, "gpio_bcm")
    if fan_status in {"NOT_CONFIGURED", "UNSUPPORTED"} and fan_gpio is not None and fan_mode in {"gpio", "pwm"}:
        raise ConfigError("[fan] gpio_bcm set while status is NOT_CONFIGURED.")

    off_below = _optional_float(fan, "off_below_c", 55.0)
    on_above = _optional_float(fan, "on_above_c", 65.0)
    if on_above <= off_below:
        raise ConfigError("[fan] on_above_c must be greater than off_below_c (hysteresis).")

    return HardwareConfig(
        profile_name=profile_name,
        verification=_optional_str(profile, "verification", "UNVERIFIED_AGAINST_PCB"),
        active_level=active_level,
        pull=pull,
        debounce_ms=debounce_ms,
        long_press_ms=long_press_ms,
        lockout_ms=lockout_ms,
        poll_ms=poll_ms,
        left_button=left_btn,
        right_button=right_btn,
        encoder_enabled=_optional_bool(encoder, "enabled", False),
        encoder_status=encoder_status,
        encoder_gpio_a=enc_a,
        encoder_gpio_b=enc_b,
        encoder_gpio_button=enc_btn,
        left_led_status=left_led_status,
        right_led_status=right_led_status,
        left_led_gpio=left_led,
        right_led_gpio=right_led,
        fan_mode=fan_mode,
        fan_status=fan_status,
        fan_gpio=fan_gpio,
        fan_off_below_c=off_below,
        fan_on_above_c=on_above,
        fan_warning_c=_optional_float(fan, "warning_c", 80.0),
        fan_critical_c=_optional_float(fan, "critical_c", 90.0),
        shutdown_method=_optional_str(power, "shutdown_method", "systemd"),
        reboot_method=_optional_str(power, "reboot_method", "systemd"),
    )


def parse_minebox(data: Mapping[str, Any], hardware: HardwareConfig, *, source: str = "", hardware_source: str = "") -> MineBoxConfig:
    device = _as_dict(data.get("device"), "device")
    api = _as_dict(data.get("api"), "api")
    dashboard = _as_dict(data.get("dashboard"), "dashboard")
    minecraft = _as_dict(data.get("minecraft"), "minecraft")
    network = _as_dict(data.get("network"), "network")
    display = _as_dict(data.get("display"), "display")
    hw = _as_dict(data.get("hardware"), "hardware")
    backup = _as_dict(data.get("backup"), "backup")
    updates = _as_dict(data.get("updates"), "updates")
    logging = _as_dict(data.get("logging"), "logging")
    paths = _as_dict(data.get("paths"), "paths")

    display_mode = _optional_str(display, "mode", "curses").lower()
    if display_mode not in {"curses", "graphical"}:
        raise ConfigError("[display] mode must be curses or graphical.")

    level = _optional_str(logging, "level", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("[logging] level must be a standard log level name.")

    supported = _str_list(minecraft, "supported_providers", ["vanilla", "paper"])
    experimental = _str_list(
        minecraft,
        "experimental_providers",
        ["fabric", "forge", "neoforge"],
    )
    overlap = set(supported) & set(experimental)
    if overlap:
        raise ConfigError(
            f"[minecraft] providers cannot be both supported and experimental: {sorted(overlap)}"
        )

    profile_name = _optional_str(hw, "profile", hardware.profile_name).lower()
    if profile_name != hardware.profile_name and profile_name in {"raspberry_pi5", "mock", "cm5"}:
        # Allow minebox.toml to override profile name used by the factory.
        hardware = replace(hardware, profile_name=profile_name)

    api_port = _optional_int(api, "port", 8080, min_v=1, max_v=65535)
    dash_port = _optional_int(dashboard, "port", api_port, min_v=1, max_v=65535)

    return MineBoxConfig(
        device_name=_optional_str(device, "name", "MineBox"),
        hostname=_optional_str(device, "hostname", "minebox"),
        api_bind=_optional_str(api, "bind_address", "0.0.0.0"),
        api_port=api_port,
        dashboard_bind=_optional_str(dashboard, "bind_address", "0.0.0.0"),
        dashboard_port=dash_port,
        minecraft_data_path=_optional_str(minecraft, "data_path", "/opt/minecraft"),
        java_path=_optional_str(minecraft, "java_path", "java"),
        default_memory_gb=_optional_int(minecraft, "default_memory_gb", 4, min_v=1, max_v=64),
        service_name=_optional_str(minecraft, "service_name", "minecraft.service"),
        supported_providers=supported,
        experimental_providers=experimental,
        hotspot_ssid=_optional_str(network, "hotspot_ssid", "MineBox-Setup"),
        hotspot_subnet=_optional_str(network, "hotspot_subnet", "192.168.4.0/24"),
        hotspot_address=_optional_str(network, "hotspot_address", "192.168.4.1"),
        hotspot_interface_role=_optional_str(network, "hotspot_interface_role", "prefer_usb_wifi"),
        client_interface_role=_optional_str(
            network, "client_interface_role", "prefer_remaining_wifi_or_ethernet"
        ),
        internet_sharing=_optional_bool(network, "internet_sharing", True),
        display_mode=display_mode,
        display_width=_optional_int(display, "width", 800, min_v=320, max_v=4096),
        display_height=_optional_int(display, "height", 480, min_v=240, max_v=2160),
        display_fallback=_optional_str(display, "fallback", "curses").lower(),
        hardware_profile=hardware.profile_name,
        hardware_profile_file=_optional_str(hw, "profile_file", "/etc/minebox/hardware.toml"),
        backup_directory=_optional_str(backup, "directory", "/opt/minecraft/backups"),
        backup_retention_count=_optional_int(backup, "retention_count", 10, min_v=1, max_v=1000),
        preserve_last_backup=_optional_bool(backup, "preserve_last_backup", True),
        update_channel=_optional_str(updates, "channel", "stable").lower(),
        logging_level=level,
        logging_directory=_optional_str(logging, "directory", "/var/log/minebox"),
        runtime_state=_optional_str(paths, "runtime_state", "/var/lib/minebox"),
        config_dir=_optional_str(paths, "config_dir", "/etc/minebox"),
        secrets_file=_optional_str(paths, "secrets_file", "/etc/minebox/secrets.env"),
        hardware=hardware,
        source_path=source,
        hardware_source_path=hardware_source,
    )


def load_toml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration file {path}: {exc}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration root in {path} must be a table.")
    return data


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def load_config(
    minebox_path: Path | None = None,
    hardware_path: Path | None = None,
) -> MineBoxConfig:
    """Load and validate configuration. Raises ConfigError with readable text."""
    if minebox_path is None:
        minebox_path = _first_existing(default_search_paths())
    if minebox_path is None:
        raise ConfigError(
            "No MineBox configuration found. Install /etc/minebox/minebox.toml "
            f"or set MINEBOX_CONFIG. Example: {_repo_config_dir() / 'minebox.example.toml'}"
        )

    data = load_toml(minebox_path)
    hw_section = _as_dict(data.get("hardware"), "hardware")
    profile_file = _optional_str(hw_section, "profile_file", "/etc/minebox/hardware.toml")

    if hardware_path is None:
        hardware_path = _first_existing(default_hardware_search_paths(profile_file))
    if hardware_path is None:
        raise ConfigError(
            "No hardware configuration found. Install /etc/minebox/hardware.toml "
            f"or set MINEBOX_HARDWARE_CONFIG. Example: {_repo_config_dir() / 'hardware.example.toml'}"
        )

    hardware = parse_hardware(load_toml(hardware_path), source=str(hardware_path))
    # Allow [hardware] profile in minebox.toml to select mock on desktops.
    override_profile = os.environ.get("MINEBOX_HARDWARE_PROFILE", "").strip().lower()
    if override_profile in {"raspberry_pi5", "mock", "cm5"}:
        hardware = replace(hardware, profile_name=override_profile)

    return parse_minebox(
        data,
        hardware,
        source=str(minebox_path),
        hardware_source=str(hardware_path),
    )


_cached: MineBoxConfig | None = None


def get_config(*, reload: bool = False) -> MineBoxConfig:
    global _cached
    if _cached is None or reload:
        _cached = load_config()
    return _cached


def clear_config_cache() -> None:
    global _cached
    _cached = None
