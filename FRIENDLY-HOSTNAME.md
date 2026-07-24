# Friendly MineBox hostname

MineBox uses mDNS/Bonjour so local clients can use a name instead of an IP address.

Default addresses:

- Dashboard: `http://minebox.local:8080`
- Minecraft Java server: `minebox.local` (default port `25565`)
- SSH, when enabled: `ssh minebox@minebox.local`

The name works on the MineBox hotspot and on the same Ethernet/Wi-Fi LAN. It does not replace a public internet domain for remote access.

## Changing the name

Use **Network Center → Device name**. A name such as `survival` becomes:

- `http://survival.local:8080`
- `survival.local` in Minecraft

Names may contain lowercase letters, numbers, and hyphens. The change restarts Avahi advertising and normally appears within a few seconds.
