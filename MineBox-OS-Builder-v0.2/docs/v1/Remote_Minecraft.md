# Remote Minecraft — Prototype v1.0

## Defaults

Remote Minecraft over Tailscale is **off by default**.

## Enable

Authenticated admin sets `expose_minecraft=true` via `/api/v1/remote-access/exposure` after Tailscale is connected.

## How friends connect

- **Local players:** SoftAP `192.168.4.1:25565` or LAN IP — no Tailscale required
- **Remote friends:** Join the same Tailscale tailnet (or an owner-approved share) and connect to the MineBox Tailscale IPv4/hostname shown only to authenticated admins — port **25565**
- No UPnP, no router port-forward automation, no public WAN relay

## Display

Local kiosk shows exposure state only — never Tailscale auth material or keys.
