# Developer Guide — MineBox OS Prototype v1.0

## Tree

Canonical product code: `MineBox-OS-Builder-v0.2/app`  
Image stage: `pi-gen/stage-minebox`  
Config examples: `config/`  
Docs: `docs/v1/`  
Tests: `tests/`

## Local API / tests (desktop)

```powershell
$env:PYTHONPATH = "app"
$env:MINEBOX_FORCE_MOCK_HARDWARE = "1"
$env:MINEBOX_HARDWARE_PROFILE = "mock"
$env:MINEBOX_CONFIG = "$PWD\config\minebox.example.toml"
$env:MINEBOX_HARDWARE_CONFIG = "$PWD\config\hardware.example.toml"
$env:MINEBOX_RUNTIME_DIR = "$PWD\.test-runtime"
python -m unittest discover -s tests -v
```

Dev dashboard helpers: `app/scripts/minebox_display_dev.py` (sets dev/mock flags).

## Version

Authoritative: repo/`VERSION` and `app/VERSION` → `core.version.get_version()`.

## Image build

Linux + Docker: `./check-project.sh && ./build.sh --docker` — [Image_Build.md](Image_Build.md).

## Conventions

- Do not invent GPIO; unresolved pins stay `NOT_CONFIGURED`
- Prefer repairing existing modules over rewrites
- Privileged ops via sudoers helpers only
- OpenAPI only with `MINEBOX_DEV_MODE=1` or `MINEBOX_ENABLE_DOCS=1`

## Packaging

```bash
python scripts/build_release_package.py
```

Produces `releases/MineBox_OS_Prototype_v1.0/` and archives with checksums.
