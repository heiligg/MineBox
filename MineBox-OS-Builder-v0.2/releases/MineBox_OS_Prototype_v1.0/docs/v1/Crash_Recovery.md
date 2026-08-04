# Crash Recovery — Prototype v1.0

## Detection

Lifecycle marks `CRASHED` when:

- start fails
- process exits before health evidence within startup timeout
- (future) supervisor observes unexpected exit

Reasons are persisted (secrets redacted) in `/var/lib/minebox/crash_history.json`.

## Policy

`services/crash_recovery.py`:

- `auto_restart` **disabled by default** (conservative)
- `max_attempts` (default 3)
- `cooldown_s` (default 120)
- Blocks infinite restart loops

## Recovery

`POST /api/v1/minecraft/recover` clears `CRASHED`/`ERROR` to `STOPPED` and starts.

systemd also has `StartLimitBurst=5` / `StartLimitIntervalSec=300` on `minecraft.service`.

## Status

`GET /api/v1/status/crash`
