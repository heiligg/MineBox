async function api(path, method = "GET") {
    const response = await fetch(path, { method });

    if (!response.ok) {
        console.error(await response.text());
        return null;
    }

    return await response.json();
}

async function refresh() {
    const data = await api("/api/v1/status");

    if (!data) return;

    document.getElementById("status").textContent =
        data.minecraft.status;

    document.getElementById("players").textContent =
        data.minecraft.players;

    document.getElementById("version").textContent =
        data.minecraft.version;

    document.getElementById("uptime").textContent =
        data.minecraft.uptime;

    document.getElementById("cpu").textContent =
        data.system.cpu_percent + "%";

    document.getElementById("ram").textContent =
        data.system.memory_percent + "%";
}

async function startServer() {
    await api("/api/v1/minecraft/start", "POST");
    await refresh();
}

async function stopServer() {
    await api("/api/v1/minecraft/stop", "POST");
    await refresh();
}

async function restartServer() {
    await api("/api/v1/minecraft/restart", "POST");
    await refresh();
}

window.onload = () => {
    refresh();
    setInterval(refresh, 5000);
};