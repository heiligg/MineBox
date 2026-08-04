# Hardware Diagnostics — Local Display

Screen: **Hardware diagnostics** on the 800×480 UI (also reachable from System).

## Live indicators

- Left button active/idle  
- Right button active/idle  
- Encoder press active/idle  
- Last encoder/button event type  
- LED capability (expected `NOT_CONFIGURED` until pinout verified)  
- Fan capability (`NOT_CONFIGURED` unless platform auto cooling reported elsewhere)  
- Hardware profile name  
- GPIO verification status from HAL snapshot  

## Safety

While diagnostics is open, navigation events update indicators only. They do **not** start/stop Minecraft, create backups, or power the device.

API: `GET /api/v1/display/events?diagnostics=1` and `hardware_diag` inside `/api/v1/display/snapshot`. Foundation `GET /api/v1/hardware/diag` remains available for the web dashboard.

## Encoder hardware

Real encoder GPIO remains **NOT_CONFIGURED**. Diagnostics validates the event bridge via mock/keyboard injection until PCB pinout is verified.
