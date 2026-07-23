# MineBox OS Builder v0.2

This package builds a 64-bit Raspberry Pi 5 image that boots into the MineBox appliance interface.

## What v0.2 fixes

The earlier builder incorrectly copied its custom configuration into `pi-gen/config/`. Current pi-gen already uses a regular file named `config`, so that path caused:

```text
realpath: config/minebox-pi5.conf: Not a directory
```

v0.2 stores the MineBox configuration as `minebox-pi5.conf` in the pi-gen root and passes that filename directly to pi-gen.

It also:

- clones pi-gen's 64-bit `arm64` branch for Raspberry Pi 5;
- uses Raspberry Pi OS based on Debian Trixie;
- prevents the Minecraft service from starting until `server.jar` exists;
- orders first-boot initialization before the MineBox UI;
- removes an invalid supplementary group from the UI service;
- uses the distribution's default headless Java runtime;
- checks shell scripts and Python files before building.

## Build

From the extracted folder:

```bash
./check-project.sh
./build.sh --docker
```

The first build can take a long time and needs tens of gigabytes of free disk space. Completed files are copied into `output/`.

## Default recovery login

- Username: `minebox`
- Password: `minebox`

SSH is disabled. The recovery login is intended for the local console on tty2. Change this before distributing an image to anyone else.

## Important current limits

- The image does not include a copyrighted Minecraft server JAR.
- The exact 5-inch display driver and GPIO pin mapping are not included until the screen and controls are connected and identified.
- This builder has been statically validated, but a full image build was not run inside this environment because it requires Docker, privileged loop devices, internet access, and substantial disk space.
