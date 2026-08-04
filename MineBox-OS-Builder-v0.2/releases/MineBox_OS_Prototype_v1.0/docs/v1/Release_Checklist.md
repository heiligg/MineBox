# Release Checklist — MineBox OS Prototype v1.0

Use with [Final_Release_Audit.md](Final_Release_Audit.md) and `RELEASE_MANIFEST.json`.

## Software gates

- [ ] `VERSION` = `1.0.0-prototype.1` everywhere checked by tests
- [ ] Full unittest suite green
- [ ] Release-specific tests green
- [ ] No runtime credentials in archive
- [ ] OpenAPI off by default
- [ ] Mock hardware not forced on appliance API path
- [ ] First-boot check script present
- [ ] Docs paths/commands match code

## Package gates

- [ ] `releases/MineBox_OS_Prototype_v1.0/` populated
- [ ] `MineBox_OS_Prototype_v1.0.tar.gz` (+ optional `.zip`)
- [ ] `SHA256SUMS` generated and verified
- [ ] Archive extraction validation passed
- [ ] Manifest image status honest
- [ ] Manifest physical validation honest
- [ ] GPIO uncertainty disclosed

## Image gates (optional for classification A)

- [ ] Linux Docker `./build.sh --docker` succeeded
- [ ] `.img.xz` named and checksummed
- [ ] No fake image artifact

## Hardware gates (never implied by software release)

- [ ] [Prototype_Hardware_Test_Plan.md](Prototype_Hardware_Test_Plan.md) executed on device
- [ ] Failures triaged

## Classification

Choose exactly one:

- [ ] **A** — Software validated, image built, hardware test pending
- [ ] **B** — Software package validated, image build pending
- [ ] **C** — Blocked — release blockers remain
