import os
import shutil
import socket
import time


def get_cpu_usage() -> float:
    with open("/proc/stat", "r", encoding="utf-8") as stat_file:
        first = stat_file.readline().split()

    idle_1 = int(first[4])
    total_1 = sum(int(value) for value in first[1:])

    time.sleep(0.2)

    with open("/proc/stat", "r", encoding="utf-8") as stat_file:
        second = stat_file.readline().split()

    idle_2 = int(second[4])
    total_2 = sum(int(value) for value in second[1:])

    idle_difference = idle_2 - idle_1
    total_difference = total_2 - total_1

    if total_difference == 0:
        return 0.0

    usage = 100.0 * (1.0 - idle_difference / total_difference)
    return round(usage, 1)


def get_memory_usage() -> float:
    memory_values = {}

    with open("/proc/meminfo", "r", encoding="utf-8") as memory_file:
        for line in memory_file:
            key, value = line.split(":", 1)
            memory_values[key] = int(value.strip().split()[0])

    total = memory_values["MemTotal"]
    available = memory_values["MemAvailable"]
    used = total - available

    return round((used / total) * 100, 1)


def get_disk_usage() -> float:
    usage = shutil.disk_usage("/")
    return round((usage.used / usage.total) * 100, 1)


def get_ip_address() -> str:
    network_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        network_socket.connect(("8.8.8.8", 80))
        return network_socket.getsockname()[0]
    except OSError:
        return "Not connected"
    finally:
        network_socket.close()


def get_uptime() -> str:
    with open("/proc/uptime", "r", encoding="utf-8") as uptime_file:
        total_seconds = int(float(uptime_file.readline().split()[0]))

    days, remaining = divmod(total_seconds, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, _ = divmod(remaining, 60)

    if days > 0:
        return f"{days}d {hours}h {minutes}m"

    return f"{hours}h {minutes}m"


def get_temperature() -> str:
    temperature_path = "/sys/class/thermal/thermal_zone0/temp"

    if not os.path.exists(temperature_path):
        return "Unavailable"

    try:
        with open(temperature_path, "r", encoding="utf-8") as temperature_file:
            temperature = int(temperature_file.read().strip()) / 1000

        return f"{temperature:.1f} C"
    except (OSError, ValueError):
        return "Unavailable"


def get_system_status() -> dict[str, str | float]:
    return {
        "cpu": get_cpu_usage(),
        "memory": get_memory_usage(),
        "disk": get_disk_usage(),
        "temperature": get_temperature(),
        "ip_address": get_ip_address(),
        "uptime": get_uptime(),
    }