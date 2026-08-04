# Backup and Restore — Prototype v1.0

## Locations

- Backups: `/opt/minecraft/backups/world-<server>-<timestamp>.tar.gz`
- Checksums: sibling `.sha256` files
- Manifest inside archive: `minebox-manifest.json`
- World data: `/opt/minecraft/servers/<id>/world`

## Create sequence (server running)

1. Operation lock (`BACKUP`)
2. Health check
3. RCON `save-all` / `save-all flush`
4. RCON `save-off` when supported
5. Archive world + manifest to `.partial` then atomic replace
6. Validate archive (`world/level.dat`, `world/region`)
7. Write SHA-256 checksum
8. Retention prune (**never deletes the only backup** when `preserve_last_backup`)
9. Always attempt `save-on` in `finally`

Stopped servers skip live save / save-off.

## Restore

```http
POST /api/v1/backups/{filename}/restore?confirm=true
```

or JSON body `{ "confirm": true }`.

Sequence: validate + checksum → extract staging → stop server → safety backup → atomic world swap → verify → start if previously running → rollback on failure.

Path traversal and non-`world/` members (except manifest) are rejected.
