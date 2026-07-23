# MineBox OS remaining hardware work

The software image foundation is ready for Pi 5 testing. These items intentionally wait for the physical hardware:

1. Exact display overlay and resolution configuration.
2. Backlight PWM or display-controller brightness driver.
3. Rotary encoder GPIO pins and debounce behavior.
4. Left and right button GPIO pins and debounce behavior.
5. Screen sleep/wake behavior.
6. Boot splash artwork fitted to the panel's native resolution.
7. Radxa CM5 bootloader, kernel, and device-tree target.

After hardware testing, the next OS-hardening milestone is a read-only root filesystem with a separate writable data partition and a recovery/update strategy.
