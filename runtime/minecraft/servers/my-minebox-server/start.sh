#!/bin/bash
set -e
cd /home/minebox/MineBox-OS-Builder-v0.2/runtime/minecraft/servers/my-minebox-server
exec java -Xms4G -Xmx4G -jar server.jar nogui
