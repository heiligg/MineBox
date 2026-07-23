async function api(path, method = "GET") {
    try {
        const response = await fetch(path, { method });
        const data = await response.json();

        if (!response.ok) {
            console.error(data);
            return null;
        }

        return data;
    } catch (error) {
        console.error("MineBox API request failed:", error);
        return null;
    }
}

function setText(id, value) {
    const element = document.getElementById(id);

    if (element) {
        element.textContent = value ?? "Unavailable";
    }
}

async function refreshStatus() {
    const data = await api("/api/v1/status");

    if (!data) {
        setText("dashboard-message", "Unable to contact MineBox API.");
        return;
    }

    setText("dashboard-message", "");
    setText("status", data.minecraft.status);
    setText("players", data.minecraft.players);
    setText("version", data.minecraft.version);
    setText("uptime", data.minecraft.uptime);
    setText("cpu", data.system.cpu_percent + "%");
    setText("ram", data.system.memory_percent + "%");
}

async function refreshConsole() {
    const data = await api("/api/v1/console?lines=150");
    const consoleElement = document.getElementById("console");

    if (!consoleElement) {
        return;
    }

    if (!data) {
        consoleElement.textContent = "Unable to load console.";
        return;
    }

    const consoleData = data.console;

    if (!consoleData.available) {
        consoleElement.textContent =
            consoleData.message || "Minecraft console is unavailable.";
        return;
    }

    const wasNearBottom =
        consoleElement.scrollHeight -
            consoleElement.scrollTop -
            consoleElement.clientHeight <
        60;

    consoleElement.textContent =
        consoleData.lines.length > 0
            ? consoleData.lines.join("\n")
            : "The Minecraft log is currently empty.";

    if (wasNearBottom) {
        consoleElement.scrollTop = consoleElement.scrollHeight;
    }
}

async function runServerAction(action) {
    setText("dashboard-message", `${action} request in progress...`);

    const data = await api(
        `/api/v1/minecraft/${action}`,
        "POST"
    );

    if (!data) {
        setText(
            "dashboard-message",
            `Unable to ${action} the Minecraft server.`
        );
        return;
    }

    setText(
        "dashboard-message",
        data.message || `${action} request completed.`
    );

    await refreshStatus();
    await refreshConsole();
}

async function startServer() {
    await runServerAction("start");
}

async function stopServer() {
    await runServerAction("stop");
}

async function restartServer() {
    await runServerAction("restart");
}

window.onload = () => {
    refreshStatus();
    refreshConsole();

    setInterval(refreshStatus, 5000);
    setInterval(refreshConsole, 2000);
};
