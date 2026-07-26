"use strict";

(() => {
    const API_BASE = "/api/v1/join";

    let panel;
    let note;
    let lanValue;
    let lanIpValue;
    let internetValue;
    let statusValue;
    let message;
    let enableButton;
    let disableButton;
    let refreshButton;
    let busy = false;

    function injectStyles() {
        if (document.getElementById("minebox-join-styles")) {
            return;
        }

        const style = document.createElement("style");
        style.id = "minebox-join-styles";
        style.textContent = `
            .join-panel { scroll-margin-top: 24px; }
            .join-grid {
                display: grid;
                gap: 12px;
                margin-top: 18px;
            }
            .join-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                padding: 12px 0;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
            .join-row:last-child { border-bottom: 0; }
            .join-label {
                color: var(--muted);
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .join-value {
                color: var(--text);
                font-size: 16px;
                font-weight: 800;
                text-align: right;
                word-break: break-all;
            }
            .join-value.ok { color: #8ee895; }
            .join-value.warn { color: #ffd27a; }
            .join-notes {
                display: grid;
                gap: 8px;
                margin-top: 16px;
                color: var(--muted);
                font-size: 14px;
                line-height: 1.45;
            }
            .join-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 16px;
            }
            .join-button {
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 10px 14px;
            }
            .join-button.primary {
                background: #2f6fed;
                border-color: #2f6fed;
            }
            .join-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .join-message {
                display: none;
                margin-top: 14px;
                padding: 12px 14px;
                border-radius: 10px;
                font-size: 14px;
            }
            .join-message.visible { display: block; }
            .join-message.success {
                background: rgba(80, 180, 100, 0.15);
                color: #8ee895;
            }
            .join-message.warning {
                background: rgba(255, 180, 60, 0.12);
                color: #ffd27a;
            }
            .join-message.error {
                background: rgba(220, 80, 80, 0.12);
                color: #ff9c9c;
            }
        `;
        document.head.appendChild(style);
    }

    function injectNav() {
        const nav = document.querySelector(".sidebar-nav, nav, .nav");
        if (!nav || document.getElementById("join-nav-item")) {
            return;
        }

        const link = document.createElement("a");
        link.id = "join-nav-item";
        link.className = "nav-item";
        link.href = "#join";
        link.innerHTML = `
            <span class="nav-icon" aria-hidden="true">+</span>
            <span class="nav-text">How to join</span>
        `;

        const networkLink = [...nav.querySelectorAll(".nav-item")]
            .find(item => item.textContent.trim().includes("Network"));
        if (networkLink) {
            nav.insertBefore(link, networkLink.nextSibling);
        } else {
            nav.appendChild(link);
        }
    }

    function injectPanel() {
        if (document.getElementById("join")) {
            panel = document.getElementById("join");
            return true;
        }

        const networkPanel = document.getElementById("network");
        const settingsPanel = document.getElementById("settings");
        const target = networkPanel || settingsPanel;
        if (!target || !target.parentNode) {
            return false;
        }

        panel = document.createElement("article");
        panel.id = "join";
        panel.className = "panel section join-panel";

        const header = document.createElement("div");
        header.className = "section-header";

        const copy = document.createElement("div");
        const title = document.createElement("h2");
        title.className = "section-title";
        title.textContent = "How to join";

        note = document.createElement("span");
        note.className = "section-note";
        note.textContent = "Loading join addresses…";

        copy.append(title, note);
        header.appendChild(copy);

        const grid = document.createElement("div");
        grid.className = "join-grid";

        function row(label, id) {
            const wrap = document.createElement("div");
            wrap.className = "join-row";
            const left = document.createElement("span");
            left.className = "join-label";
            left.textContent = label;
            const value = document.createElement("strong");
            value.className = "join-value";
            value.id = id;
            value.textContent = "…";
            wrap.append(left, value);
            grid.appendChild(wrap);
            return value;
        }

        lanValue = row("Home network (best)", "join-lan-value");
        lanIpValue = row("Home network IP", "join-lan-ip-value");
        internetValue = row("Internet address", "join-internet-value");
        statusValue = row("Internet access", "join-status-value");

        const notes = document.createElement("div");
        notes.className = "join-notes";
        notes.id = "join-notes";

        const actions = document.createElement("div");
        actions.className = "join-actions";

        refreshButton = document.createElement("button");
        refreshButton.type = "button";
        refreshButton.className = "join-button";
        refreshButton.textContent = "Refresh";
        refreshButton.addEventListener("click", () => loadStatus(true));

        enableButton = document.createElement("button");
        enableButton.type = "button";
        enableButton.className = "join-button primary";
        enableButton.textContent = "Enable internet join";
        enableButton.addEventListener("click", enableInternet);

        disableButton = document.createElement("button");
        disableButton.type = "button";
        disableButton.className = "join-button";
        disableButton.textContent = "Disable internet join";
        disableButton.addEventListener("click", disableInternet);

        actions.append(refreshButton, enableButton, disableButton);

        message = document.createElement("div");
        message.className = "join-message";
        message.id = "join-message";

        panel.append(header, grid, notes, actions, message);
        target.parentNode.insertBefore(panel, target.nextSibling);
        return true;
    }

    function showMessage(text, type) {
        message.textContent = text || "";
        message.className = text
            ? `join-message visible ${type || ""}`.trim()
            : "join-message";
    }

    function setBusy(state) {
        busy = state;
        refreshButton.disabled = state;
        enableButton.disabled = state;
        disableButton.disabled = state;
    }

    async function parseResponse(response) {
        let data = {};
        try {
            data = await response.json();
        } catch {
            data = {};
        }

        if (!response.ok) {
            const detail = data.detail;
            if (detail && typeof detail === "object") {
                if (detail.join) {
                    render(detail.join);
                }
                throw new Error(
                    detail.message ||
                    `Request failed with status ${response.status}.`
                );
            }
            throw new Error(
                typeof detail === "string"
                    ? detail
                    : `Request failed with status ${response.status}.`
            );
        }

        return data;
    }

    function render(data) {
        lanValue.textContent = data.lan_address || "Unavailable";
        lanIpValue.textContent = data.lan_ip_address || "Unavailable";
        internetValue.textContent =
            data.internet_address || "Unavailable";

        if (data.internet_mapped) {
            statusValue.textContent = "Port forwarded";
            statusValue.className = "join-value ok";
        } else if (data.internet_address) {
            statusValue.textContent = "Needs router port forward";
            statusValue.className = "join-value warn";
        } else {
            statusValue.textContent = "No public IP detected";
            statusValue.className = "join-value warn";
        }

        const notes = document.getElementById("join-notes");
        notes.replaceChildren();
        for (const line of data.notes || []) {
            const p = document.createElement("div");
            p.textContent = line;
            notes.appendChild(p);
        }

        note.textContent =
            `Updated · ${new Date().toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit"
            })}`;
    }

    async function loadStatus(announce) {
        if (busy) {
            return;
        }

        setBusy(true);
        try {
            const response = await fetch(`${API_BASE}/status`, {
                cache: "no-store"
            });
            const data = await parseResponse(response);
            render(data);
            if (announce) {
                showMessage("Join addresses refreshed.", "success");
            }
            // Best-effort: keep Avahi advertisement fresh.
            fetch(`${API_BASE}/refresh-avahi`, { method: "POST" }).catch(
                () => {}
            );
        } catch (error) {
            showMessage(
                error.message || "Could not load join addresses.",
                "error"
            );
        } finally {
            setBusy(false);
        }
    }

    async function enableInternet() {
        if (busy) {
            return;
        }

        setBusy(true);
        showMessage("Requesting router port forward…", "warning");
        try {
            const response = await fetch(`${API_BASE}/internet/enable`, {
                method: "POST"
            });
            const data = await parseResponse(response);
            if (data.join) {
                render(data.join);
            }
            showMessage(
                data.message || "Internet join enabled.",
                "success"
            );
        } catch (error) {
            showMessage(
                error.message ||
                "Could not enable automatic internet join.",
                "error"
            );
        } finally {
            setBusy(false);
        }
    }

    async function disableInternet() {
        if (busy) {
            return;
        }

        setBusy(true);
        try {
            const response = await fetch(`${API_BASE}/internet/disable`, {
                method: "POST"
            });
            const data = await parseResponse(response);
            if (data.join) {
                render(data.join);
            }
            showMessage(
                data.message || "Internet join disabled.",
                "success"
            );
        } catch (error) {
            showMessage(
                error.message || "Could not disable internet join.",
                "error"
            );
        } finally {
            setBusy(false);
        }
    }

    function boot() {
        injectStyles();
        injectNav();
        if (!injectPanel()) {
            window.setTimeout(boot, 400);
            return;
        }
        loadStatus(false);
        window.setInterval(() => loadStatus(false), 30000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
