"use strict";

(() => {
    const SETTINGS_API = "/api/v1/minecraft/settings";
    const APPLIANCE_API = "/api/v1/appliance";
    const RESTART_API = "/api/v1/minecraft/restart";

    const fields = [
        {
            key: "motd",
            label: "Server name / MOTD",
            description: "The message displayed in the Minecraft server list.",
            type: "text",
            maxlength: 120,
            placeholder: "MineBox Minecraft Server"
        },
        {
            key: "max-players",
            label: "Maximum players",
            description: "The maximum number of players allowed online.",
            type: "number",
            min: 1,
            max: 1000
        },
        {
            key: "gamemode",
            label: "Gamemode",
            description:
                "Sets creative/survival for the world and players. Applied to everyone when you save.",
            type: "select",
            options: [
                ["survival", "Survival"],
                ["creative", "Creative"],
                ["adventure", "Adventure"],
                ["spectator", "Spectator"]
            ]
        },
        {
            key: "difficulty",
            label: "Difficulty",
            description:
                "Controls hostile mobs and survival difficulty. Applied live when you save.",
            type: "select",
            options: [
                ["peaceful", "Peaceful"],
                ["easy", "Easy"],
                ["normal", "Normal"],
                ["hard", "Hard"]
            ]
        },
        {
            key: "view-distance",
            label: "View distance",
            description: "Maximum chunk distance sent to players.",
            type: "number",
            min: 2,
            max: 32
        },
        {
            key: "simulation-distance",
            label: "Simulation distance",
            description: "Distance in which entities and game systems are updated.",
            type: "number",
            min: 2,
            max: 32
        },
        {
            key: "server-port",
            label: "Server port",
            description: "The network port players use to connect.",
            type: "number",
            min: 1024,
            max: 65535
        },
        {
            key: "player-idle-timeout",
            label: "Idle timeout",
            description: "Minutes before an inactive player is kicked. Use 0 to disable.",
            type: "number",
            min: 0,
            max: 1440
        },
        {
            key: "online-mode",
            label: "Online mode",
            description:
                "Verify player accounts with Minecraft. Turning this off lets LAN players join without a Microsoft login, but uses a different player UUID — MineBox copies your inventory across when the setting changes.",
            type: "checkbox"
        },
        {
            key: "pvp",
            label: "Player versus player",
            description: "Allow players to damage one another.",
            type: "checkbox"
        },
        {
            key: "white-list",
            label: "Whitelist",
            description: "Only allow approved players to join.",
            type: "checkbox"
        },
        {
            key: "allow-flight",
            label: "Allow flight",
            description: "Prevent the server from kicking players detected as flying.",
            type: "checkbox"
        },
        {
            key: "enable-command-block",
            label: "Command blocks",
            description: "Allow command blocks to run server commands.",
            type: "checkbox"
        },
        {
            key: "force-gamemode",
            label: "Force gamemode",
            description:
                "Reset every player to the server gamemode when they join. Kept on when you change gamemode from MineBox.",
            type: "checkbox"
        }
    ];

    const applianceFields = [
        {
            key: "memory_gb",
            label: "JVM memory (GB)",
            description:
                "Heap size for the Minecraft process. Takes effect after a restart.",
            type: "number",
            min: 1,
            max: 64
        },
        {
            key: "scheduled_restart_time",
            label: "Daily restart time",
            description:
                "24-hour HH:MM local time (for example 04:30). Leave blank to disable.",
            type: "text",
            maxlength: 5,
            placeholder: "04:30"
        },
        {
            key: "automatic_backup_hours",
            label: "Automatic backup interval (hours)",
            description:
                "Create a world backup every N hours. Use 0 to disable.",
            type: "number",
            min: 0,
            max: 720
        }
    ];

    let form;
    let message;
    let refreshNote;
    let saveButton;
    let saveRestartButton;
    let reloadButton;
    let settingsLoaded = false;
    let requestRunning = false;

    function injectStyles() {
        const style = document.createElement("style");

        style.textContent = `
            .settings-panel {
                scroll-margin-top: 24px;
            }

            .settings-header-copy {
                display: grid;
                gap: 5px;
            }

            .settings-form {
                display: grid;
                gap: 22px;
                margin-top: 22px;
            }

            .settings-group {
                display: grid;
                gap: 14px;
            }

            .settings-group-title {
                margin: 0;
                color: var(--text);
                font-size: 15px;
                font-weight: 800;
            }

            .settings-grid {
                display: grid;
                grid-template-columns:
                    repeat(2, minmax(0, 1fr));
                gap: 14px;
            }

            .settings-field {
                display: grid;
                align-content: start;
                gap: 7px;
                min-width: 0;
                padding: 16px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 13px;
                background: rgba(255, 255, 255, 0.025);
            }

            .settings-field-label {
                color: var(--text);
                font-size: 14px;
                font-weight: 750;
            }

            .settings-field-description {
                min-height: 34px;
                color: var(--muted);
                font-size: 12px;
                line-height: 1.45;
            }

            .settings-input,
            .settings-select {
                width: 100%;
                min-height: 42px;
                box-sizing: border-box;
                padding: 9px 11px;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 9px;
                outline: none;
                color: var(--text);
                background: rgba(7, 12, 18, 0.9);
                font: inherit;
            }

            .settings-input:focus,
            .settings-select:focus {
                border-color: rgba(101, 212, 110, 0.7);
                box-shadow: 0 0 0 3px rgba(101, 212, 110, 0.11);
            }

            .settings-select option {
                color: #f2f5f7;
                background: #111820;
            }

            .settings-toggle-list {
                display: grid;
                grid-template-columns:
                    repeat(2, minmax(0, 1fr));
                gap: 12px;
            }

            .settings-toggle {
                display: flex;
                align-items: flex-start;
                gap: 12px;
                min-height: 76px;
                padding: 15px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 13px;
                background: rgba(255, 255, 255, 0.025);
                cursor: pointer;
            }

            .settings-toggle:hover {
                border-color: rgba(101, 212, 110, 0.25);
            }

            .settings-toggle input {
                width: 18px;
                height: 18px;
                margin: 2px 0 0;
                accent-color: #65d46e;
                flex: 0 0 auto;
            }

            .settings-toggle-copy {
                display: grid;
                gap: 4px;
            }

            .settings-toggle-title {
                color: var(--text);
                font-size: 14px;
                font-weight: 750;
            }

            .settings-toggle-description {
                color: var(--muted);
                font-size: 12px;
                line-height: 1.45;
            }

            .settings-actions {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 10px;
                padding-top: 4px;
            }

            .settings-button {
                min-height: 42px;
                padding: 0 16px;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 9px;
                color: var(--text);
                background: var(--panel-light);
                font: inherit;
                font-size: 13px;
                font-weight: 800;
                cursor: pointer;
            }

            .settings-button:hover:not(:disabled) {
                border-color: rgba(101, 212, 110, 0.4);
            }

            .settings-button.primary {
                border-color: rgba(101, 212, 110, 0.45);
                color: #071008;
                background: #65d46e;
            }

            .settings-button.restart {
                border-color: rgba(244, 183, 64, 0.45);
                color: #171005;
                background: #f4b740;
            }

            .settings-button:disabled {
                opacity: 0.55;
                cursor: not-allowed;
            }

            .settings-message {
                display: none;
                padding: 12px 14px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                font-size: 13px;
                line-height: 1.5;
            }

            .settings-message.visible {
                display: block;
            }

            .settings-message.success {
                border-color: rgba(101, 212, 110, 0.35);
                color: #a9efae;
                background: rgba(101, 212, 110, 0.08);
            }

            .settings-message.warning {
                border-color: rgba(244, 183, 64, 0.4);
                color: #ffd47c;
                background: rgba(244, 183, 64, 0.08);
            }

            .settings-message.error {
                border-color: rgba(255, 102, 102, 0.4);
                color: #ffaaaa;
                background: rgba(255, 102, 102, 0.08);
            }

            .settings-error {
                min-height: 16px;
                color: #ff9e9e;
                font-size: 11px;
            }

            .settings-dirty-note {
                margin-left: auto;
                color: var(--muted);
                font-size: 12px;
            }

            @media (max-width: 860px) {
                .settings-grid,
                .settings-toggle-list {
                    grid-template-columns: 1fr;
                }
            }

            @media (max-width: 600px) {
                .settings-actions {
                    align-items: stretch;
                }

                .settings-button {
                    width: 100%;
                }

                .settings-dirty-note {
                    width: 100%;
                    margin-left: 0;
                    text-align: center;
                }
            }
        `;

        document.head.appendChild(style);
    }

    function createField(field) {
        if (field.type === "checkbox") {
            const label = document.createElement("label");
            label.className = "settings-toggle";

            const input = document.createElement("input");
            input.type = "checkbox";
            input.name = field.key;
            input.dataset.setting = field.key;

            const copy = document.createElement("span");
            copy.className = "settings-toggle-copy";

            const title = document.createElement("span");
            title.className = "settings-toggle-title";
            title.textContent = field.label;

            const description = document.createElement("span");
            description.className =
                "settings-toggle-description";
            description.textContent = field.description;

            copy.append(title, description);
            label.append(input, copy);

            return label;
        }

        const wrapper = document.createElement("label");
        wrapper.className = "settings-field";

        const title = document.createElement("span");
        title.className = "settings-field-label";
        title.textContent = field.label;

        const description = document.createElement("span");
        description.className =
            "settings-field-description";
        description.textContent = field.description;

        let input;

        if (field.type === "select") {
            input = document.createElement("select");
            input.className = "settings-select";

            for (const [value, label] of field.options) {
                const option = document.createElement("option");
                option.value = value;
                option.textContent = label;
                input.appendChild(option);
            }
        } else {
            input = document.createElement("input");
            input.className = "settings-input";
            input.type = field.type;

            if (field.min !== undefined) {
                input.min = String(field.min);
            }

            if (field.max !== undefined) {
                input.max = String(field.max);
            }

            if (field.maxlength !== undefined) {
                input.maxLength = field.maxlength;
            }

            if (field.placeholder) {
                input.placeholder = field.placeholder;
            }
        }

        input.name = field.key;
        input.dataset.setting = field.key;

        const error = document.createElement("span");
        error.className = "settings-error";
        error.dataset.errorFor = field.key;

        wrapper.append(title, description, input, error);

        return wrapper;
    }

    function createGroup(titleText, selectedFields, className) {
        const group = document.createElement("section");
        group.className = "settings-group";

        const title = document.createElement("h3");
        title.className = "settings-group-title";
        title.textContent = titleText;

        const grid = document.createElement("div");
        grid.className = className;

        for (const field of selectedFields) {
            grid.appendChild(createField(field));
        }

        group.append(title, grid);

        return group;
    }

    function injectNavigation() {
        const nav = document.querySelector(".nav");

        if (!nav || document.getElementById("settings-nav-item")) {
            return;
        }

        const link = document.createElement("a");
        link.id = "settings-nav-item";
        link.className = "nav-item";
        link.href = "#settings";

        const icon = document.createElement("span");
        icon.className = "nav-icon";
        icon.textContent = "⚙";

        const text = document.createElement("span");
        text.className = "nav-text";
        text.textContent = "Settings";

        link.append(icon, text);

        const setupLink = [...nav.querySelectorAll(".nav-item")]
            .find(item =>
                item.textContent.trim().includes("Setup")
            );

        if (setupLink) {
            nav.insertBefore(link, setupLink);
        } else {
            nav.appendChild(link);
        }
    }

    function injectPanel() {
        const backups = document.getElementById("backups");

        if (!backups || document.getElementById("settings")) {
            return false;
        }

        const panel = document.createElement("article");
        panel.id = "settings";
        panel.className = "panel section settings-panel";

        const header = document.createElement("div");
        header.className = "section-header";

        const headerCopy = document.createElement("div");
        headerCopy.className = "settings-header-copy";

        const heading = document.createElement("h2");
        heading.className = "section-title";
        heading.textContent = "Server settings";

        refreshNote = document.createElement("span");
        refreshNote.className = "section-note";
        refreshNote.textContent = "Loading server settings…";

        headerCopy.append(heading, refreshNote);
        header.appendChild(headerCopy);

        form = document.createElement("form");
        form.className = "settings-form";
        form.id = "server-settings-form";

        const standardFields = fields.filter(field =>
            field.type !== "checkbox"
        );

        const toggleFields = fields.filter(field =>
            field.type === "checkbox"
        );

        form.append(
            createGroup(
                "Server configuration",
                standardFields,
                "settings-grid"
            ),
            createGroup(
                "Gameplay options",
                toggleFields,
                "settings-toggle-list"
            ),
            createGroup(
                "MineBox appliance",
                applianceFields,
                "settings-grid"
            )
        );

        message = document.createElement("div");
        message.id = "settings-message";
        message.className = "settings-message";
        message.setAttribute("role", "status");
        message.setAttribute("aria-live", "polite");

        const actions = document.createElement("div");
        actions.className = "settings-actions";

        saveButton = document.createElement("button");
        saveButton.type = "submit";
        saveButton.className = "settings-button primary";
        saveButton.textContent = "Save Settings";

        saveRestartButton = document.createElement("button");
        saveRestartButton.type = "button";
        saveRestartButton.className =
            "settings-button restart";
        saveRestartButton.textContent = "Save & Restart";

        reloadButton = document.createElement("button");
        reloadButton.type = "button";
        reloadButton.className = "settings-button";
        reloadButton.textContent = "Reload Values";

        const dirtyNote = document.createElement("span");
        dirtyNote.id = "settings-dirty-note";
        dirtyNote.className = "settings-dirty-note";
        dirtyNote.textContent = "No unsaved changes";

        actions.append(
            saveButton,
            saveRestartButton,
            reloadButton,
            dirtyNote
        );

        form.append(message, actions);
        panel.append(header, form);

        backups.parentNode.insertBefore(panel, backups);

        return true;
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

            if (
                detail &&
                typeof detail === "object"
            ) {
                const error = new Error(
                    detail.message ||
                    `Request failed with status ${response.status}.`
                );

                error.validationErrors =
                    detail.errors || {};

                throw error;
            }

            throw new Error(
                typeof detail === "string"
                    ? detail
                    : `Request failed with status ${response.status}.`
            );
        }

        return data;
    }

    function setBusy(busy, action = "save") {
        requestRunning = busy;

        for (
            const control of
            form.querySelectorAll("input, select, button")
        ) {
            control.disabled = busy;
        }

        saveButton.textContent = busy && action === "save"
            ? "Saving…"
            : "Save Settings";

        saveRestartButton.textContent =
            busy && action === "restart"
                ? "Saving & Restarting…"
                : "Save & Restart";

        reloadButton.textContent =
            busy && action === "reload"
                ? "Loading…"
                : "Reload Values";
    }

    function showMessage(text, type = "") {
        message.textContent = text;
        message.className =
            `settings-message visible ${type}`.trim();
    }

    function clearMessage() {
        message.textContent = "";
        message.className = "settings-message";
    }

    function clearErrors() {
        for (
            const error of
            form.querySelectorAll(".settings-error")
        ) {
            error.textContent = "";
        }
    }

    function showValidationErrors(errors) {
        clearErrors();

        for (const [key, text] of Object.entries(errors)) {
            const error = form.querySelector(
                `[data-error-for="${CSS.escape(key)}"]`
            );

            if (error) {
                error.textContent = text;
            }
        }
    }

    function populateForm(settings, appliance = {}) {
        for (const field of fields) {
            const input = form.elements[field.key];

            if (!input || !(field.key in settings)) {
                continue;
            }

            if (field.type === "checkbox") {
                input.checked = Boolean(settings[field.key]);
            } else {
                input.value = String(settings[field.key]);
            }
        }

        for (const field of applianceFields) {
            const input = form.elements[field.key];
            if (!input) {
                continue;
            }
            const value = appliance[field.key];
            if (value === undefined || value === null) {
                input.value = field.key === "scheduled_restart_time" ? "" : "0";
            } else {
                input.value = String(value);
            }
        }

        settingsLoaded = true;
        form.dataset.dirty = "false";
        updateDirtyNote();
    }

    function collectSettings() {
        const result = {};

        for (const field of fields) {
            const input = form.elements[field.key];

            if (field.type === "checkbox") {
                result[field.key] = input.checked;
            } else if (field.type === "number") {
                result[field.key] = Number(input.value);
            } else {
                result[field.key] = input.value.trim();
            }
        }

        return result;
    }

    function collectAppliance() {
        const result = {};
        for (const field of applianceFields) {
            const input = form.elements[field.key];
            if (!input) {
                continue;
            }
            if (field.type === "number") {
                result[field.key] = Number(input.value);
            } else {
                result[field.key] = input.value.trim();
            }
        }
        return result;
    }

    function updateDirtyNote() {
        const note =
            document.getElementById("settings-dirty-note");

        if (!note) {
            return;
        }

        note.textContent =
            form.dataset.dirty === "true"
                ? "Unsaved changes"
                : "No unsaved changes";
    }

    function validateForm() {
        clearErrors();

        let valid = true;
        const allFields = fields.concat(applianceFields);

        for (const field of allFields) {
            const input = form.elements[field.key];

            if (
                field.type !== "checkbox" &&
                input &&
                !input.checkValidity()
            ) {
                valid = false;

                const error = form.querySelector(
                    `[data-error-for="${CSS.escape(field.key)}"]`
                );

                if (error) {
                    error.textContent =
                        input.validationMessage;
                }
            }
        }

        const restartInput = form.elements.scheduled_restart_time;
        if (restartInput && restartInput.value.trim()) {
            const ok = /^\d{1,2}:\d{2}$/.test(restartInput.value.trim());
            if (!ok) {
                valid = false;
                const error = form.querySelector(
                    '[data-error-for="scheduled_restart_time"]'
                );
                if (error) {
                    error.textContent = "Use HH:MM, such as 04:30.";
                }
            }
        }

        return valid;
    }

    async function loadSettings(showStatus = true) {
        if (requestRunning) {
            return;
        }

        setBusy(true, "reload");
        clearErrors();

        if (showStatus) {
            clearMessage();
            refreshNote.textContent =
                "Loading server settings…";
        }

        try {
            const [settingsResponse, applianceResponse] = await Promise.all([
                fetch(SETTINGS_API, { method: "GET", cache: "no-store" }),
                fetch(APPLIANCE_API, { method: "GET", cache: "no-store" }),
            ]);

            const data = await parseResponse(settingsResponse);
            const appliance = await parseResponse(applianceResponse);

            populateForm(data.settings || {}, appliance);

            refreshNote.textContent =
                `Loaded · ${new Date().toLocaleTimeString(
                    [],
                    {
                        hour: "numeric",
                        minute: "2-digit"
                    }
                )}`;

            if (showStatus) {
                showMessage(
                    "Current server settings loaded.",
                    "success"
                );
            }
        } catch (error) {
            refreshNote.textContent =
                "Settings unavailable";

            showMessage(
                error.message ||
                "MineBox could not load the server settings.",
                "error"
            );
        } finally {
            setBusy(false);
        }
    }

    async function saveSettings(restartAfterSave = false) {
        if (requestRunning || !settingsLoaded) {
            return;
        }

        if (!validateForm()) {
            showMessage(
                "Correct the highlighted settings before saving.",
                "error"
            );
            return;
        }

        setBusy(
            true,
            restartAfterSave ? "restart" : "save"
        );

        clearErrors();
        clearMessage();

        try {
            const applianceBody = collectAppliance();
            const [response, applianceResponse] = await Promise.all([
                fetch(SETTINGS_API, {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        settings: collectSettings(),
                        restart: Boolean(restartAfterSave)
                    })
                }),
                fetch(APPLIANCE_API, {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(applianceBody)
                }),
            ]);

            const data = await parseResponse(response);
            const appliance = await parseResponse(applianceResponse);

            populateForm(data.settings || {}, appliance);

            form.dataset.dirty = "false";
            updateDirtyNote();

            const parts = [];
            if (data.message) {
                parts.push(data.message);
            }
            if (appliance.message) {
                parts.push(appliance.message);
            }
            if (
                appliance.restart_required_for_memory
                && !restartAfterSave
            ) {
                parts.push("Restart Minecraft to apply the new JVM memory.");
            }

            if (data.applied || restartAfterSave) {
                showMessage(
                    parts.join(" ") ||
                    "Settings saved and Minecraft restarted so they take effect.",
                    "success"
                );

                refreshNote.textContent =
                    "Saved and applied";
            } else {
                showMessage(
                    parts.join(" ") ||
                    "Settings saved.",
                    "success"
                );

                refreshNote.textContent =
                    "Saved";
            }

            if (
                typeof window.refreshStatus === "function"
            ) {
                await window.refreshStatus();
            }
        } catch (error) {
            if (error.validationErrors) {
                showValidationErrors(
                    error.validationErrors
                );
            }

            showMessage(
                error.message ||
                "The settings could not be saved.",
                "error"
            );

            refreshNote.textContent =
                "Settings save failed";
        } finally {
            setBusy(false);
        }
    }

    function attachEvents() {
        form.addEventListener(
            "submit",
            event => {
                event.preventDefault();
                saveSettings(false);
            }
        );

        saveRestartButton.addEventListener(
            "click",
            () => saveSettings(true)
        );

        reloadButton.addEventListener(
            "click",
            () => loadSettings(true)
        );

        form.addEventListener(
            "input",
            () => {
                form.dataset.dirty = "true";
                updateDirtyNote();
                clearMessage();
            }
        );

        form.addEventListener(
            "change",
            () => {
                form.dataset.dirty = "true";
                updateDirtyNote();
                clearMessage();
            }
        );

        window.addEventListener(
            "beforeunload",
            event => {
                if (form.dataset.dirty !== "true") {
                    return;
                }

                event.preventDefault();
                event.returnValue = "";
            }
        );
    }

    function initialize() {
        injectStyles();
        injectNavigation();

        if (!injectPanel()) {
            console.error(
                "MineBox Settings could not find the backups panel."
            );
            return;
        }

        attachEvents();
        loadSettings(false);
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            initialize,
            { once: true }
        );
    } else {
        initialize();
    }
})();
