# MineBox Updater v2

MineBox now uses the same transactional update process in development and on the appliance.

## Update flow

1. The dashboard fetches update metadata.
2. A detached updater clones the selected release into a sibling `.update` directory.
3. The updater verifies that the release contains the MineBox API, updater, and launcher.
4. Runtime data and the local Python environment are moved to a shared `.data` directory and linked into each release.
5. The running dashboard stops only after validation succeeds.
6. The current and staged directories are atomically swapped.
7. MineBox restarts and must pass its HTTP health check.
8. A failed health check automatically restores `.previous`.

The source repository must publish a compatible branch containing at least:

- `app/api/server.py`
- `app/services/updates.py`
- `app/scripts/minebox_updater.py`
- `run-dashboard.sh`

Development and appliance installs use the same updater. Their only difference is how the service restarts: development relaunches `run-dashboard.sh`, while production restarts `minebox-api.service`.
