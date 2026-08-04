# MineBox hotspot internet sharing

MineBox uses NetworkManager's `ipv4.method shared` mode. Devices connected to
`MineBox-Setup` receive DHCP and DNS from MineBox, and their internet traffic is
NAT-routed through the current upstream connection.

## Supported configurations

- **Ethernet internet + built-in Wi-Fi hotspot:** fully supported and preferred.
- **Wi-Fi internet + second Wi-Fi adapter hotspot:** fully supported.
- **One Wi-Fi adapter for both internet and hotspot:** intentionally not enabled.
  Most Raspberry Pi Wi-Fi radios cannot reliably remain a client and access point
  at the same time. MineBox keeps the internet connection and reports that a
  second adapter or Ethernet is required.
- **No internet:** the hotspot stays available for the dashboard and local
  Minecraft access.

The hotspot gateway and dashboard address is `http://192.168.4.1`.
