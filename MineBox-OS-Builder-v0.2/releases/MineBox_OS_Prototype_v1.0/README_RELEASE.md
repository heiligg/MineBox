# MineBox_OS_Prototype_v1.0

**Version:** `1.0.0-prototype.1`

**Classification:** B — Software package validated, image build pending

Prototype — not mass-production ready. Physical hardware validation is separate.

## Contents

- `installer/` — idempotent install.sh
- `source/app/` — application tree
- `config/` — example configs (safe placeholders)
- `systemd/` — unit files
- `sudoers/` — allowlist
- `pi-gen/` — image stage (app embedded at build time)
- `scripts/` — validation, SoftAP render, OTA apply, build helpers
- `docs/` — documentation
- `validation_reports/` — security + test summaries

## Install

```bash
sudo bash installer/install.sh
```

## Image build

On Linux: copy stage into a builder checkout and run `./build.sh --docker`.
No `.img` is included in this package unless separately generated and listed in the manifest.
