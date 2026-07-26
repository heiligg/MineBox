"use strict";

(() => {
    const API_BASE = "/api/v1/players";

    let panel;
    let note;
    let message;
    let onlineList;
    let opsList;
    let whitelistList;
    let bansList;
    let nameInput;
    let reasonInput;
    let whitelistBadge;
    let busy = false;

    function injectStyles() {
        if (document.getElementById("minebox-players-styles")) {
            return;
        }
        const style = document.createElement("style");
        style.id = "minebox-players-styles";
        style.textContent = `
            .players-panel { scroll-margin-top: 24px; }
            .players-toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                align-items: center;
                margin-top: 16px;
            }
            .players-toolbar input {
                flex: 1 1 140px;
                min-width: 120px;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                font: inherit;
                padding: 10px 12px;
            }
            .players-button {
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 8px 12px;
            }
            .players-button.primary {
                background: #2f6fed;
                border-color: #2f6fed;
            }
            .players-button.danger { color: #ff9c9c; }
            .players-button:disabled { opacity: 0.5; cursor: not-allowed; }
            .players-grid {
                display: grid;
                gap: 18px;
                margin-top: 18px;
            }
            @media (min-width: 900px) {
                .players-grid {
                    grid-template-columns: 1fr 1fr;
                }
            }
            .players-section h3 {
                margin: 0 0 8px;
                font-size: 14px;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--muted);
            }
            .players-badge {
                display: inline-block;
                margin-left: 8px;
                padding: 2px 8px;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 700;
                background: rgba(255,255,255,0.08);
                color: var(--muted);
            }
            .players-badge.on {
                background: rgba(80, 180, 100, 0.18);
                color: #8ee895;
            }
            .players-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                padding: 10px 0;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
            .players-row:last-child { border-bottom: 0; }
            .players-name { font-weight: 800; }
            .players-actions { display: flex; flex-wrap: wrap; gap: 6px; }
            .players-empty {
                color: var(--muted);
                font-size: 14px;
                padding: 8px 0;
            }
            .players-message {
                display: none;
                margin-top: 14px;
                padding: 12px 14px;
                border-radius: 10px;
                font-size: 14px;
            }
            .players-message.visible { display: block; }
            .players-message.success {
                background: rgba(80, 180, 100, 0.15);
                color: #8ee895;
            }
            .players-message.error {
                background: rgba(220, 80, 80, 0.12);
                color: #ff9c9c;
            }
            .players-message.warning {
                background: rgba(255, 180, 60, 0.12);
                color: #ffd27a;
            }
        `;
        document.head.appendChild(style);
    }

    function injectNav() {
        const nav = document.querySelector(".sidebar-nav, nav, .nav");
        if (!nav || document.getElementById("players-nav-item")) {
            return;
        }
        const link = document.createElement("a");
        link.id = "players-nav-item";
        link.className = "nav-item";
        link.href = "#players";
        link.innerHTML = `
            <span class="nav-icon" aria-hidden="true">♟</span>
            <span class="nav-text">Players</span>
        `;
        const consoleLink = [...nav.querySelectorAll(".nav-item")].find(
            (item) => item.getAttribute("href") === "#console"
                || item.textContent.trim().includes("Console")
        );
        if (consoleLink) {
            nav.insertBefore(link, consoleLink);
        } else {
            nav.appendChild(link);
        }
    }

    function showMessage(text, type = "") {
        if (!message) {
            return;
        }
        message.textContent = text || "";
        message.className = `players-message${text ? ` visible ${type}` : ""}`.trim();
    }

    function detailFromPayload(payload) {
        if (!payload) {
            return "Request failed.";
        }
        if (typeof payload.detail === "string") {
            return payload.detail;
        }
        if (typeof payload.message === "string") {
            return payload.message;
        }
        return "Request failed.";
    }

    async function api(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                Accept: "application/json",
                ...(options.body ? { "Content-Type": "application/json" } : {}),
                ...(options.headers || {}),
            },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(detailFromPayload(payload));
        }
        return payload;
    }

    function renderNameList(container, names, actionsBuilder) {
        container.innerHTML = "";
        if (!names || !names.length) {
            const empty = document.createElement("div");
            empty.className = "players-empty";
            empty.textContent = "None";
            container.appendChild(empty);
            return;
        }
        for (const name of names) {
            const row = document.createElement("div");
            row.className = "players-row";
            const label = document.createElement("span");
            label.className = "players-name";
            label.textContent = name;
            const actions = document.createElement("div");
            actions.className = "players-actions";
            for (const action of actionsBuilder(name)) {
                actions.appendChild(action);
            }
            row.append(label, actions);
            container.appendChild(row);
        }
    }

    function actionButton(label, className, handler) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `players-button ${className || ""}`.trim();
        button.textContent = label;
        button.addEventListener("click", handler);
        return button;
    }

    function render(payload) {
        const online = payload.online || [];
        const max = payload.max_players;
        note.textContent = payload.server_running
            ? (payload.rcon_available
                ? `Online ${online.length}${max ? `/${max}` : ""}`
                : "Server running — RCON unavailable")
            : "Server offline — JSON edits only (kick disabled)";

        whitelistBadge.textContent = payload.whitelist_enabled
            ? "Whitelist on"
            : "Whitelist off";
        whitelistBadge.className = `players-badge${
            payload.whitelist_enabled ? " on" : ""
        }`;

        renderNameList(onlineList, online, (name) => [
            actionButton("Op", "primary", () => runAction("op", name)),
            actionButton("Whitelist", "", () => runAction("whitelist/add", name)),
            actionButton("Kick", "danger", () => runAction("kick", name)),
            actionButton("Ban", "danger", () => runAction("ban", name)),
        ]);
        renderNameList(opsList, payload.ops || [], (name) => [
            actionButton("De-op", "danger", () => runAction("deop", name)),
        ]);
        renderNameList(whitelistList, payload.whitelist || [], (name) => [
            actionButton("Remove", "danger", () => runAction("whitelist/remove", name)),
        ]);
        renderNameList(bansList, payload.bans || [], (name) => [
            actionButton("Pardon", "primary", () => runAction("pardon", name)),
        ]);
    }

    async function loadStatus() {
        if (busy) {
            return;
        }
        busy = true;
        try {
            const payload = await api(API_BASE);
            render(payload);
        } catch (error) {
            showMessage(error.message || "Could not load players.", "error");
            note.textContent = "Unable to load players";
        } finally {
            busy = false;
        }
    }

    async function runAction(action, name, reason = "") {
        if (busy) {
            return;
        }
        busy = true;
        showMessage("");
        try {
            const payload = await api(`${API_BASE}/${action}`, {
                method: "POST",
                body: JSON.stringify({ name, reason }),
            });
            showMessage(`${action.replace("/", " ")}: ${name}`, "success");
            render(payload);
            nameInput.value = "";
            reasonInput.value = "";
        } catch (error) {
            showMessage(error.message || "Action failed.", "error");
        } finally {
            busy = false;
        }
    }

    function currentName() {
        return (nameInput.value || "").trim();
    }

    function injectPanel() {
        if (document.getElementById("players")) {
            panel = document.getElementById("players");
            return true;
        }
        const consolePanel = document.getElementById("console");
        const backups = document.getElementById("backups");
        const target = consolePanel || backups;
        if (!target || !target.parentNode) {
            return false;
        }

        panel = document.createElement("article");
        panel.id = "players";
        panel.className = "panel section players-panel";

        const header = document.createElement("div");
        header.className = "section-header";
        const copy = document.createElement("div");
        const title = document.createElement("h2");
        title.className = "section-title";
        title.textContent = "Players";
        note = document.createElement("span");
        note.className = "section-note";
        note.textContent = "Loading…";
        copy.append(title, note);
        header.appendChild(copy);

        const toolbar = document.createElement("div");
        toolbar.className = "players-toolbar";
        nameInput = document.createElement("input");
        nameInput.type = "text";
        nameInput.placeholder = "Player name";
        nameInput.maxLength = 16;
        reasonInput = document.createElement("input");
        reasonInput.type = "text";
        reasonInput.placeholder = "Reason (kick/ban)";
        reasonInput.maxLength = 200;

        const mk = (label, className, action) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `players-button ${className || ""}`.trim();
            button.textContent = label;
            button.addEventListener("click", () => {
                const name = currentName();
                if (!name) {
                    showMessage("Enter a player name first.", "warning");
                    return;
                }
                runAction(action, name, reasonInput.value || "");
            });
            return button;
        };

        toolbar.append(
            nameInput,
            reasonInput,
            mk("Op", "primary", "op"),
            mk("Whitelist", "", "whitelist/add"),
            mk("Kick", "danger", "kick"),
            mk("Ban", "danger", "ban"),
            (() => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "players-button";
                button.textContent = "Refresh";
                button.addEventListener("click", loadStatus);
                return button;
            })()
        );

        const grid = document.createElement("div");
        grid.className = "players-grid";

        function section(titleText, withBadge) {
            const wrap = document.createElement("div");
            wrap.className = "players-section";
            const heading = document.createElement("h3");
            heading.textContent = titleText;
            if (withBadge) {
                whitelistBadge = document.createElement("span");
                whitelistBadge.className = "players-badge";
                whitelistBadge.textContent = "Whitelist";
                heading.appendChild(whitelistBadge);
            }
            const list = document.createElement("div");
            wrap.append(heading, list);
            grid.appendChild(wrap);
            return list;
        }

        onlineList = section("Online now");
        opsList = section("Operators");
        whitelistList = section("Whitelist", true);
        bansList = section("Banned players");

        message = document.createElement("div");
        message.className = "players-message";

        panel.append(header, toolbar, grid, message);
        target.parentNode.insertBefore(panel, target);
        return true;
    }

    function boot() {
        injectStyles();
        injectNav();
        if (!injectPanel()) {
            window.setTimeout(boot, 250);
            return;
        }
        loadStatus();
        window.setInterval(loadStatus, 10000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
