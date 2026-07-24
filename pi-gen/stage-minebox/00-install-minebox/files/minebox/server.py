"""Compatibility wrapper for older MineBox imports."""
from services.minecraft import *  # noqa: F401,F403
from services.rcon import send as send_rcon_command

def is_server_running(): return is_running()
def start_server(): return start().ok
def stop_server(): return stop().ok
def restart_server(): return restart().ok
def get_status(): return status_text()
def get_player_count_text(): return player_count_text()
def get_server_version(): return version()
def get_server_uptime(): return uptime()
def get_recent_log_lines(line_count=12): return recent_logs(line_count)
