# Functional runtime fixes

This build separates local dashboard development from the final OS runtime.

When `run-dashboard.sh` is used, MineBox now stores test Minecraft servers under:

`runtime/minecraft/`

The final built OS still defaults to `/opt/minecraft`.

Changes in this build:

- Server creation no longer requires write access to `/opt` during local development.
- Start, stop, and restart use a locally tracked Java process in development mode.
- The final OS continues to use the `minecraft.service` systemd unit.
- The setup download screen now times out after three minutes and displays an error instead of spinning forever.
- Start errors now clearly report a missing `server.jar` or `start.sh`.
