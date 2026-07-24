"use strict";

(() => {
    const API_BASE = "/api/v1/update";

    let panel;
    let checkButton;
    let installButton;
    let message;
    let statusBadge;
    let versionValue;
    let currentCommitValue;
    let latestCommitValue;
    let channelValue;
    let branchValue;
    let repositoryValue;
    let localChangesValue;
    let serviceValue;
    let updateLog;
    let refreshNote;

    let requestRunning = false;
    let updateRunning = false;
    let refreshTimer = null;

    async function api(path, options = {}) {
        const response = await fetch(path, {
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                ...(options.headers || {})
            },
            ...options
        });

        let data = {};

        try {
            data = await response.json();
        } catch {
            data = {};
        }

        if (!response.ok) {
            const detail = data.detail;

            if (typeof detail === "string") {
                throw new Error(detail);
            }

            if (detail && typeof detail.message === "string") {
                throw new Error(detail.message);
            }

            throw new Error(
                `Update request failed with status ${response.status}.`
            );
        }

        return data;
    }

    function displayValue(value, fallback = "Unavailable") {
        if (value === null || value === undefined || value === "") {
            return fallback;
        }

        return String(value);
    }

    function formatState(state) {
        const labels = {
            unknown: "Unknown",
            checking: "Checking",
            updating: "Updating",
            up_to_date: "Up to date",
            update_available: "Update available",
            success: "Updated",
            failed: "Failed"
        };

        return labels[state] || String(state || "Unknown")
            .replaceAll("_", " ")
            .replace(/\b\w/g, character => character.toUpperCase());
    }

    function showMessage(text, type = "") {
        message.textContent = text;
        message.className =
            `update-message visible ${type}`.trim();
    }

    function clearMessage() {
        message.textContent = "";
        message.className = "update-message";
    }

    function setBusy(busy, action = "") {
        requestRunning = busy;

        checkButton.disabled = busy || updateRunning;
        installButton.disabled = busy || updateRunning;

        checkButton.textContent =
            busy && action === "check"
                ? "Checking…"
                : "Check for Updates";

        installButton.textContent =
            busy && action === "install"
                ? "Starting Update…"
                : updateRunning
                    ? "Update Running…"
                    : "Install Update";
    }

    function determineState(data) {
        const service = data.service || {};
        const updater = data.updater || {};

        if (
            service.active_state === "activating" ||
            ["starting", "staging", "validating", "switching", "restarting"].includes(updater.state)
        ) {
            return "updating";
        }

        if (updater.state === "failed") {
            return "failed";
        }

        if (data.update_available) {
            return "update_available";
        }

        if (data.repository_available) {
            return "up_to_date";
        }

        return updater.state || "unknown";
    }

    function renderStatus(data) {
        const updater = data.updater || {};
        const service = data.service || {};
        const state = determineState(data);

        updateRunning = state === "updating";

        versionValue.textContent =
            displayValue(data.version);

        currentCommitValue.textContent =
            displayValue(
                data.current_commit_short || data.current_commit
            );

        latestCommitValue.textContent =
            displayValue(
                data.latest_commit_short || data.latest_commit
            );

        channelValue.textContent =
            displayValue(data.channel);

        branchValue.textContent =
            displayValue(data.branch);

        repositoryValue.textContent =
            data.repository_available
                ? "Connected"
                : "Unavailable";

        repositoryValue.className =
            data.repository_available
                ? "update-value success"
                : "update-value error";

        localChangesValue.textContent =
            data.local_changes
                ? "Uncommitted changes"
                : "Clean";

        localChangesValue.className =
            data.local_changes
                ? "update-value warning"
                : "update-value success";

        serviceValue.textContent =
            formatState(
                service.active_state ||
                updater.state ||
                "unknown"
            );

        statusBadge.textContent = formatState(state);
        statusBadge.className =
            `update-status-badge ${state}`;

        installButton.disabled =
            requestRunning ||
            updateRunning ||
            !data.update_available ||
            !data.repository_available;

        checkButton.disabled =
            requestRunning || updateRunning;

        installButton.textContent =
            updateRunning
                ? "Update Running…"
                : "Install Update";

        refreshNote.textContent =
            `Updated ${new Date().toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit",
                second: "2-digit"
            })}`;

        if (data.local_changes) {
            showMessage(
                "MineBox has uncommitted changes. They will be saved automatically before the update is installed.",
                "warning"
            );
        } else if (
            !requestRunning &&
            !updateRunning &&
            message.dataset.automatic === "true"
        ) {
            clearMessage();
        }
    }

    async function refreshStatus({ silent = true } = {}) {
        try {
            const data = await api(`${API_BASE}/status`);
            renderStatus(data);
            return data;
        } catch (error) {
            statusBadge.textContent = "Unavailable";
            statusBadge.className =
                "update-status-badge failed";

            if (!silent) {
                showMessage(error.message, "error");
            }

            throw error;
        }
    }

    async function refreshLog() {
        try {
            const data = await api(
                `${API_BASE}/log?lines=150`
            );

            const wasNearBottom =
                updateLog.scrollHeight -
                    updateLog.scrollTop -
                    updateLog.clientHeight <
                70;

            updateLog.textContent =
                data.log || "No update activity has been recorded yet.";

            if (wasNearBottom) {
                updateLog.scrollTop =
                    updateLog.scrollHeight;
            }
        } catch (error) {
            updateLog.textContent =
                `Unable to load update log: ${error.message}`;
        }
    }

    async function checkForUpdates() {
        if (requestRunning || updateRunning) {
            return;
        }

        clearMessage();
        setBusy(true, "check");

        try {
            const data = await api(
                `${API_BASE}/check`,
                { method: "POST" }
            );

            renderStatus(data);

            showMessage(
                data.message ||
                    (
                        data.update_available
                            ? "A MineBox update is available."
                            : "MineBox is already up to date."
                    ),
                data.update_available ? "warning" : "success"
            );

            await refreshLog();
        } catch (error) {
            showMessage(error.message, "error");
        } finally {
            setBusy(false);
        }
    }

    async function installUpdate() {
        if (
            requestRunning ||
            updateRunning ||
            installButton.disabled
        ) {
            return;
        }

        const confirmed = window.confirm(
            "Install the available MineBox update now? " +
            "The MineBox web service may briefly restart."
        );

        if (!confirmed) {
            return;
        }

        clearMessage();
        setBusy(true, "install");

        try {
            const data = await api(
                `${API_BASE}/install`,
                { method: "POST" }
            );

            updateRunning = true;

            showMessage(
                data.message || "The MineBox update has started.",
                "success"
            );

            await refreshStatus({ silent: true });
            await refreshLog();
        } catch (error) {
            showMessage(error.message, "error");
            updateRunning = false;
        } finally {
            setBusy(false);
        }
    }

    async function automaticRefresh() {
        try {
            await refreshStatus({ silent: true });
        } catch {
            // The web service may briefly disappear during an update.
        }

        await refreshLog();
    }

    function initialize() {
        panel = document.getElementById("updates");

        if (!panel) {
            return;
        }

        checkButton =
            document.getElementById("update-check-button");

        installButton =
            document.getElementById("update-install-button");

        message =
            document.getElementById("update-message");

        statusBadge =
            document.getElementById("update-status-badge");

        versionValue =
            document.getElementById("update-version-value");

        currentCommitValue =
            document.getElementById(
                "update-current-commit-value"
            );

        latestCommitValue =
            document.getElementById(
                "update-latest-commit-value"
            );

        channelValue =
            document.getElementById("update-channel-value");

        branchValue =
            document.getElementById("update-branch-value");

        repositoryValue =
            document.getElementById(
                "update-repository-value"
            );

        localChangesValue =
            document.getElementById(
                "update-local-changes-value"
            );

        serviceValue =
            document.getElementById("update-service-value");

        updateLog =
            document.getElementById("update-log");

        refreshNote =
            document.getElementById("update-refresh-note");

        message.dataset.automatic = "true";

        checkButton.addEventListener(
            "click",
            checkForUpdates
        );

        installButton.addEventListener(
            "click",
            installUpdate
        );

        Promise.allSettled([
            refreshStatus({ silent: false }),
            refreshLog()
        ]);

        refreshTimer = window.setInterval(
            automaticRefresh,
            5000
        );
    }

    window.addEventListener(
        "DOMContentLoaded",
        initialize
    );

    window.addEventListener(
        "beforeunload",
        () => {
            if (refreshTimer !== null) {
                window.clearInterval(refreshTimer);
            }
        }
    );
})();
