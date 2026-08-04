from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any

from services import network


CHECK_INTERVAL_SECONDS = int(
    os.environ.get(
        "MINEBOX_NETWORK_CHECK_INTERVAL",
        "15",
    )
)

STARTUP_GRACE_SECONDS = int(
    os.environ.get(
        "MINEBOX_NETWORK_STARTUP_GRACE",
        "45",
    )
)

HOTSPOT_SSID = os.environ.get(
    "MINEBOX_HOTSPOT_SSID",
    network.DEFAULT_HOTSPOT_SSID,
)

HOTSPOT_PASSWORD = os.environ.get(
    "MINEBOX_HOTSPOT_PASSWORD",
    "mineboxsetup",
)

ONE_SHOT = os.environ.get(
    "MINEBOX_NETWORK_ONE_SHOT",
    "",
).lower() in {
    "1",
    "true",
    "yes",
}


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "[minebox-network] "
        "%(levelname)s: "
        "%(message)s"
    ),
)

LOGGER = logging.getLogger("minebox-network")


def nmcli_lines(arguments: list[str]) -> list[str]:
    """
    Run nmcli and return non-empty output lines.

    Errors are treated as an empty result so the guard remains alive
    while NetworkManager is starting.
    """

    try:
        result = subprocess.run(
            [
                "nmcli",
                "--colors",
                "no",
                *arguments,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        LOGGER.warning(
            "Unable to run nmcli: %s",
            exc,
        )
        return []

    if result.returncode != 0:
        message = (
            result.stderr.strip()
            or result.stdout.strip()
        )

        if message:
            LOGGER.debug(
                "nmcli returned an error: %s",
                message,
            )

        return []

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def ethernet_is_connected() -> bool:
    """
    Return True when a wired Ethernet device is connected.
    """

    lines = nmcli_lines(
        [
            "--terse",
            "--fields",
            "TYPE,STATE",
            "device",
            "status",
        ]
    )

    for line in lines:
        fields = line.rsplit(":", 1)

        if len(fields) != 2:
            continue

        device_type, state = fields

        if (
            device_type == "ethernet"
            and state == "connected"
        ):
            return True

    return False


def regular_wifi_is_connected(
    status: dict[str, Any],
) -> bool:
    """
    Return True only for normal Wi-Fi, not the MineBox hotspot.
    """

    return bool(
        status.get("connected")
        and not status.get("hotspot_active")
        and status.get("connection_type") == "wifi"
    )


def stop_unneeded_hotspot(
    reason: str,
) -> None:
    if not network.hotspot_is_active():
        return

    LOGGER.info(
        "Stopping setup hotspot because %s.",
        reason,
    )

    result = network.stop_hotspot()

    if result.ok:
        LOGGER.info(
            "Setup hotspot stopped."
        )
    else:
        LOGGER.error(
            "Could not stop setup hotspot: %s",
            result.message,
        )


def start_setup_hotspot() -> None:
    if network.hotspot_is_active():
        LOGGER.debug(
            "Setup hotspot is already active."
        )
        return

    LOGGER.warning(
        "No usable network connection was found. "
        "Starting setup hotspot '%s'.",
        HOTSPOT_SSID,
    )

    result = network.start_hotspot(
        ssid=HOTSPOT_SSID,
        password=HOTSPOT_PASSWORD,
    )

    if result.ok:
        LOGGER.info(
            "Setup hotspot started successfully."
        )
    else:
        LOGGER.error(
            "Could not start setup hotspot: %s",
            result.message,
        )


def check_network() -> None:
    """
    Perform one network-management check.
    """

    if not network.networkmanager_available():
        LOGGER.warning(
            "NetworkManager is not ready."
        )
        return

    interface = network.wifi_interface()

    if interface is None:
        LOGGER.info(
            "No Wi-Fi adapter detected; "
            "no hotspot changes will be made."
        )
        return

    if ethernet_is_connected():
        stop_unneeded_hotspot(
            "Ethernet is connected"
        )
        return

    current_status = network.status()

    if regular_wifi_is_connected(current_status):
        stop_unneeded_hotspot(
            "normal Wi-Fi is connected"
        )
        return

    start_setup_hotspot()


def main() -> None:
    LOGGER.info(
        "MineBox automatic network guard starting."
    )

    if not ONE_SHOT:
        LOGGER.info(
            "Waiting %s seconds for normal network "
            "connections to initialize.",
            STARTUP_GRACE_SECONDS,
        )
        time.sleep(
            max(0, STARTUP_GRACE_SECONDS)
        )

    while True:
        try:
            check_network()
        except Exception:
            LOGGER.exception(
                "Unexpected network guard error."
            )

        if ONE_SHOT:
            return

        time.sleep(
            max(5, CHECK_INTERVAL_SECONDS)
        )


if __name__ == "__main__":
    main()
