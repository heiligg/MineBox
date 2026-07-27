"use strict";

(() => {
    const API_BASE = "/api/v1/network";

    let networkPanel;
    let statusMessage;
    let statusNote;
    let wifiList;
    let savedList;
    let refreshButton;
    let scanButton;
    let disconnectButton;
    let hotspotStartButton;
    let hotspotStopButton;
    let hotspotSsidInput;
    let hotspotPasswordInput;
    let requestRunning = false;
    let refreshTimer = null;

    function injectStyles() {
        if (document.getElementById("minebox-network-styles")) {
            return;
        }

        const style = document.createElement("style");
        style.id = "minebox-network-styles";

        style.textContent = `
            .network-panel {
                scroll-margin-top: 24px;
            }

            .network-header-copy {
                display: grid;
                gap: 5px;
            }

            .network-content {
                display: grid;
                gap: 20px;
                margin-top: 22px;
            }

            .network-status-grid {
                display: grid;
                grid-template-columns:
                    repeat(4, minmax(0, 1fr));
                gap: 12px;
            }

            .network-status-card {
                display: grid;
                gap: 7px;
                min-width: 0;
                padding: 15px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 13px;
                background: rgba(255, 255, 255, 0.025);
            }

            .network-status-label {
                color: var(--muted);
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.06em;
                text-transform: uppercase;
            }

            .network-status-value {
                overflow: hidden;
                color: var(--text);
                font-size: 15px;
                font-weight: 800;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .network-status-value.online {
                color: #8ee895;
            }

            .network-status-value.warning {
                color: #ffd27a;
            }

            .network-status-value.offline {
                color: #ff9c9c;
            }

            .network-section {
                display: grid;
                gap: 13px;
                padding-top: 4px;
            }

            .network-section-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }

            .network-section-title {
                margin: 0;
                color: var(--text);
                font-size: 15px;
                font-weight: 800;
            }

            .network-section-description {
                margin: -5px 0 0;
                color: var(--muted);
                font-size: 12px;
                line-height: 1.5;
            }

            .network-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 9px;
            }

            .network-button {
                min-height: 40px;
                padding: 0 14px;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 9px;
                color: var(--text);
                background: var(--panel-light);
                font: inherit;
                font-size: 12px;
                font-weight: 800;
                cursor: pointer;
            }

            .network-button:hover:not(:disabled) {
                border-color: rgba(101, 212, 110, 0.4);
            }

            .network-button.primary {
                border-color: rgba(101, 212, 110, 0.45);
                color: #071008;
                background: #65d46e;
            }

            .network-button.warning {
                border-color: rgba(244, 183, 64, 0.45);
                color: #171005;
                background: #f4b740;
            }

            .network-button.danger {
                border-color: rgba(255, 102, 102, 0.45);
                color: #fff0f0;
                background: rgba(255, 102, 102, 0.12);
            }

            .network-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .network-message {
                display: none;
                padding: 12px 14px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                font-size: 13px;
                line-height: 1.5;
            }

            .network-message.visible {
                display: block;
            }

            .network-message.success {
                border-color: rgba(101, 212, 110, 0.35);
                color: #a9efae;
                background: rgba(101, 212, 110, 0.08);
            }

            .network-message.warning {
                border-color: rgba(244, 183, 64, 0.4);
                color: #ffd47c;
                background: rgba(244, 183, 64, 0.08);
            }

            .network-message.error {
                border-color: rgba(255, 102, 102, 0.4);
                color: #ffaaaa;
                background: rgba(255, 102, 102, 0.08);
            }

            .network-list {
                display: grid;
                gap: 9px;
            }

            .network-empty {
                padding: 18px;
                border: 1px dashed rgba(255, 255, 255, 0.12);
                border-radius: 11px;
                color: var(--muted);
                font-size: 13px;
                line-height: 1.5;
                text-align: center;
            }

            .network-row {
                display: grid;
                grid-template-columns:
                    minmax(0, 1fr) auto;
                align-items: center;
                gap: 14px;
                padding: 13px 14px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 11px;
                background: rgba(255, 255, 255, 0.025);
            }

            .network-row-copy {
                display: grid;
                gap: 4px;
                min-width: 0;
            }

            .network-row-title {
                display: flex;
                align-items: center;
                gap: 8px;
                overflow: hidden;
                color: var(--text);
                font-size: 14px;
                font-weight: 800;
            }

            .network-row-title-text {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .network-row-meta {
                color: var(--muted);
                font-size: 11px;
                line-height: 1.45;
            }

            .network-badge {
                display: inline-flex;
                align-items: center;
                min-height: 20px;
                padding: 0 7px;
                border: 1px solid rgba(101, 212, 110, 0.3);
                border-radius: 999px;
                color: #a9efae;
                background: rgba(101, 212, 110, 0.08);
                font-size: 10px;
                font-weight: 800;
                white-space: nowrap;
            }

            .network-row-actions {
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .network-signal {
                display: inline-flex;
                align-items: flex-end;
                gap: 2px;
                height: 16px;
            }

            .network-signal span {
                width: 3px;
                border-radius: 2px;
                background: rgba(255, 255, 255, 0.18);
            }

            .network-signal span:nth-child(1) {
                height: 4px;
            }

            .network-signal span:nth-child(2) {
                height: 7px;
            }

            .network-signal span:nth-child(3) {
                height: 11px;
            }

            .network-signal span:nth-child(4) {
                height: 15px;
            }

            .network-signal span.active {
                background: #65d46e;
            }

            .network-form {
                display: grid;
                grid-template-columns:
                    minmax(0, 1fr)
                    minmax(0, 1fr)
                    auto;
                align-items: end;
                gap: 11px;
                padding: 15px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.025);
            }

            .network-field {
                display: grid;
                gap: 7px;
                min-width: 0;
            }

            .network-field-label {
                color: var(--text);
                font-size: 12px;
                font-weight: 800;
            }

            .network-input {
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

            .network-input:focus {
                border-color: rgba(101, 212, 110, 0.7);
                box-shadow:
                    0 0 0 3px rgba(101, 212, 110, 0.11);
            }

            .network-dialog-backdrop {
                position: fixed;
                inset: 0;
                z-index: 3000;
                display: grid;
                place-items: center;
                padding: 20px;
                background: rgba(0, 0, 0, 0.7);
            }

            .network-dialog {
                display: grid;
                gap: 16px;
                width: min(430px, 100%);
                padding: 21px;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 15px;
                background: #101821;
                box-shadow:
                    0 24px 70px rgba(0, 0, 0, 0.5);
            }

            .network-dialog h3 {
                margin: 0;
                color: var(--text);
                font-size: 18px;
            }

            .network-dialog-description {
                margin: -7px 0 0;
                color: var(--muted);
                font-size: 12px;
                line-height: 1.5;
            }

            .network-dialog-actions {
                display: flex;
                justify-content: flex-end;
                gap: 9px;
            }

            @media (max-width: 950px) {
                .network-status-grid {
                    grid-template-columns:
                        repeat(2, minmax(0, 1fr));
                }

                .network-form {
                    grid-template-columns:
                        repeat(2, minmax(0, 1fr));
                }

                .network-form .network-button {
                    grid-column: 1 / -1;
                }
            }

            @media (max-width: 620px) {
                .network-status-grid,
                .network-form {
                    grid-template-columns: 1fr;
                }

                .network-row {
                    grid-template-columns: 1fr;
                }

                .network-row-actions {
                    justify-content: flex-start;
                    flex-wrap: wrap;
                }

                .network-actions,
                .network-section-header {
                    align-items: stretch;
                    flex-direction: column;
                }

                .network-button {
                    width: 100%;
                }

                .network-dialog-actions {
                    flex-direction: column-reverse;
                }
            }
        `;

        document.head.appendChild(style);
    }

    function createButton(text, className = "") {
        const button = document.createElement("button");
        button.type = "button";
        button.className =
            `network-button ${className}`.trim();
        button.textContent = text;

        return button;
    }

    function createStatusCard(label, id) {
        const card = document.createElement("div");
        card.className = "network-status-card";

        const labelElement = document.createElement("span");
        labelElement.className = "network-status-label";
        labelElement.textContent = label;

        const value = document.createElement("strong");
        value.id = id;
        value.className = "network-status-value";
        value.textContent = "Loading…";

        card.append(labelElement, value);

        return card;
    }

    function createSection(title, description = "") {
        const section = document.createElement("section");
        section.className = "network-section";

        const header = document.createElement("div");
        header.className = "network-section-header";

        const copy = document.createElement("div");

        const heading = document.createElement("h3");
        heading.className = "network-section-title";
        heading.textContent = title;

        copy.appendChild(heading);

        if (description) {
            const descriptionElement =
                document.createElement("p");

            descriptionElement.className =
                "network-section-description";

            descriptionElement.textContent = description;
            copy.appendChild(descriptionElement);
        }

        header.appendChild(copy);
        section.appendChild(header);

        return {
            section,
            header
        };
    }

    function injectNavigation() {
        const nav = document.querySelector(".nav");

        if (
            !nav ||
            document.getElementById("network-nav-item")
        ) {
            return;
        }

        const link = document.createElement("a");
        link.id = "network-nav-item";
        link.className = "nav-item";
        link.href = "#network";

        const icon = document.createElement("span");
        icon.className = "nav-icon";
        icon.textContent = "⌁";

        const text = document.createElement("span");
        text.className = "nav-text";
        text.textContent = "Network";

        link.append(icon, text);

        const settingsLink =
            document.getElementById("settings-nav-item");

        const setupLink = [...nav.querySelectorAll(".nav-item")]
            .find(item =>
                item.textContent.trim().includes("Setup")
            );

        if (settingsLink) {
            nav.insertBefore(link, settingsLink);
        } else if (setupLink) {
            nav.insertBefore(link, setupLink);
        } else {
            nav.appendChild(link);
        }
    }

    function injectPanel() {
        if (document.getElementById("network")) {
            networkPanel = document.getElementById("network");
            return true;
        }

        const settingsPanel =
            document.getElementById("settings");

        const backupsPanel =
            document.getElementById("backups");

        const insertionTarget =
            settingsPanel || backupsPanel;

        if (!insertionTarget || !insertionTarget.parentNode) {
            return false;
        }

        const panel = document.createElement("article");
        panel.id = "network";
        panel.className = "panel section network-panel";

        const header = document.createElement("div");
        header.className = "section-header";

        const headerCopy = document.createElement("div");
        headerCopy.className = "network-header-copy";

        const heading = document.createElement("h2");
        heading.className = "section-title";
        heading.textContent = "Network Center";

        statusNote = document.createElement("span");
        statusNote.className = "section-note";
        statusNote.textContent = "Loading network status…";

        headerCopy.append(heading, statusNote);

        const headerActions =
            document.createElement("div");

        headerActions.className = "network-actions";

        refreshButton = createButton("Refresh");
        refreshButton.addEventListener(
            "click",
            () => refreshEverything(true)
        );

        headerActions.appendChild(refreshButton);
        header.append(headerCopy, headerActions);

        const content = document.createElement("div");
        content.className = "network-content";

        const statusGrid = document.createElement("div");
        statusGrid.className = "network-status-grid";

        statusGrid.append(
            createStatusCard("Connection", "network-connection"),
            createStatusCard("Network", "network-ssid"),
            createStatusCard("IP address", "network-ip"),
            createStatusCard("Hostname", "network-hostname"),
            createStatusCard("Signal", "network-signal-value"),
            createStatusCard("Security", "network-security"),
            createStatusCard("Gateway", "network-gateway"),
            createStatusCard("Adapter", "network-interface")
        );

        const connectionSection = createSection(
            "Current connection",
            "Ethernet stays online while the setup hotspot uses Wi-Fi. Disconnect only applies to a Wi-Fi client connection."
        );

        const connectionActions =
            document.createElement("div");

        connectionActions.className = "network-actions";

        disconnectButton = createButton(
            "Disconnect Wi-Fi",
            "danger"
        );

        disconnectButton.addEventListener(
            "click",
            disconnectWifi
        );

        connectionActions.appendChild(disconnectButton);
        connectionSection.header.appendChild(
            connectionActions
        );

        const wifiSection = createSection(
            "Nearby Wi-Fi networks",
            "Scan with the USB Wi-Fi adapter while the setup hotspot stays on the onboard radio."
        );

        scanButton = createButton(
            "Scan Networks",
            "primary"
        );

        scanButton.addEventListener(
            "click",
            () => loadWifiNetworks(true)
        );

        wifiSection.header.appendChild(scanButton);

        wifiList = document.createElement("div");
        wifiList.className = "network-list";
        wifiList.innerHTML =
            '<div class="network-empty">Scanning for Wi-Fi networks…</div>';

        wifiSection.section.appendChild(wifiList);

        const savedSection = createSection(
            "Saved networks",
            "Previously used Wi-Fi profiles stored by NetworkManager."
        );

        savedList = document.createElement("div");
        savedList.className = "network-list";
        savedList.innerHTML =
            '<div class="network-empty">Loading saved networks…</div>';

        savedSection.section.appendChild(savedList);

        const hotspotSection = createSection(
            "Emergency setup hotspot",
            "Create a temporary Wi-Fi network when MineBox cannot connect to your normal network."
        );

        const hotspotForm = document.createElement("form");
        hotspotForm.className = "network-form";

        const ssidField = document.createElement("label");
        ssidField.className = "network-field";

        const ssidLabel = document.createElement("span");
        ssidLabel.className = "network-field-label";
        ssidLabel.textContent = "Hotspot name";

        hotspotSsidInput =
            document.createElement("input");

        hotspotSsidInput.className = "network-input";
        hotspotSsidInput.type = "text";
        hotspotSsidInput.maxLength = 32;
        hotspotSsidInput.required = true;
        hotspotSsidInput.value = "MineBox-Setup";

        ssidField.append(ssidLabel, hotspotSsidInput);

        const passwordField =
            document.createElement("label");

        passwordField.className = "network-field";

        const passwordLabel =
            document.createElement("span");

        passwordLabel.className = "network-field-label";
        passwordLabel.textContent = "Hotspot password";

        hotspotPasswordInput =
            document.createElement("input");

        hotspotPasswordInput.className = "network-input";
        hotspotPasswordInput.type = "password";
        hotspotPasswordInput.minLength = 8;
        hotspotPasswordInput.maxLength = 63;
        hotspotPasswordInput.required = true;
        hotspotPasswordInput.placeholder =
            "At least 8 characters";

        passwordField.append(
            passwordLabel,
            hotspotPasswordInput
        );

        hotspotStartButton = createButton(
            "Start Hotspot",
            "warning"
        );

        hotspotStartButton.type = "submit";

        hotspotForm.append(
            ssidField,
            passwordField,
            hotspotStartButton
        );

        hotspotForm.addEventListener(
            "submit",
            startHotspot
        );

        hotspotStopButton = createButton(
            "Stop Hotspot",
            "danger"
        );

        hotspotStopButton.addEventListener(
            "click",
            stopHotspot
        );

        const hotspotActions =
            document.createElement("div");

        hotspotActions.className = "network-actions";
        hotspotActions.appendChild(hotspotStopButton);

        hotspotSection.section.append(
            hotspotForm,
            hotspotActions
        );

        statusMessage = document.createElement("div");
        statusMessage.id = "network-message";
        statusMessage.className = "network-message";
        statusMessage.setAttribute("role", "status");
        statusMessage.setAttribute(
            "aria-live",
            "polite"
        );

        content.append(
            statusGrid,
            statusMessage,
            connectionSection.section,
            wifiSection.section,
            savedSection.section,
            hotspotSection.section
        );

        panel.append(header, content);

        insertionTarget.parentNode.insertBefore(
            panel,
            insertionTarget
        );

        networkPanel = panel;

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

            throw new Error(
                typeof detail === "string"
                    ? detail
                    : detail?.message ||
                      `Request failed with status ${response.status}.`
            );
        }

        return data;
    }

    function showMessage(text, type = "") {
        if (!statusMessage) {
            return;
        }

        statusMessage.textContent = text;
        statusMessage.className =
            `network-message visible ${type}`.trim();
    }

    function clearMessage() {
        if (!statusMessage) {
            return;
        }

        statusMessage.textContent = "";
        statusMessage.className = "network-message";
    }

    function setBusy(busy) {
        requestRunning = busy;

        const controls = networkPanel
            ? networkPanel.querySelectorAll(
                "button, input"
            )
            : [];

        for (const control of controls) {
            control.disabled = busy;
        }
    }

    function setText(id, value, className = "") {
        const element = document.getElementById(id);

        if (!element) {
            return;
        }

        element.textContent =
            value === null ||
            value === undefined ||
            value === ""
                ? "Unavailable"
                : String(value);

        element.className =
            `network-status-value ${className}`.trim();
    }

    function updateStatus(network) {
        const available =
            Boolean(network.networkmanager_available);

        const wifiAvailable =
            Boolean(network.wifi_available);

        const ethernet = network.ethernet || {};
        const wifi = network.wifi || {};
        const hotspot = network.hotspot || {};

        const hotspotActive =
            Boolean(network.hotspot_active || hotspot.active);

        const ethernetConnected =
            Boolean(ethernet.connected);

        const wifiConnected =
            Boolean(wifi.connected);

        const connectionType =
            network.connection_type || null;

        let connectionText = "Disconnected";
        let connectionClass = "offline";

        if (!available && !ethernetConnected && !hotspotActive) {
            connectionText = "NetworkManager unavailable";
        } else if (ethernetConnected && hotspotActive) {
            connectionText = "Ethernet · Setup hotspot on";
            connectionClass = "online";
        } else if (ethernetConnected) {
            connectionText = "Ethernet connected";
            connectionClass = "online";
        } else if (wifiConnected) {
            connectionText = "Wi-Fi connected";
            connectionClass = "online";
        } else if (hotspotActive) {
            connectionText = "Setup hotspot active";
            connectionClass = "warning";
        } else if (!wifiAvailable && !ethernet.available) {
            connectionText = "No network adapters";
        }

        const networkName =
            network.display_name ||
            (
                connectionType === "ethernet"
                    ? (ethernet.connection_name || "Ethernet")
                    : connectionType === "wifi"
                        ? (network.ssid || wifi.ssid || "Wi-Fi")
                        : connectionType === "hotspot"
                            ? (hotspot.ssid || "MineBox-Setup")
                            : "Not connected"
            );

        setText(
            "network-connection",
            connectionText,
            connectionClass
        );

        setText(
            "network-ssid",
            networkName
        );

        setText(
            "network-ip",
            network.ip_address ||
                ethernet.ip_address ||
                wifi.ip_address ||
                (hotspotActive ? (hotspot.address || "192.168.4.1") : null)
        );

        setText(
            "network-hostname",
            network.local_hostname ||
                network.hostname ||
                "minebox.local"
        );

        if (
            connectionType === "wifi" &&
            network.signal !== null &&
            network.signal !== undefined
        ) {
            setText(
                "network-signal-value",
                `${network.signal}%`
            );
        } else {
            setText(
                "network-signal-value",
                connectionType === "ethernet"
                    ? "Wired"
                    : connectionType === "hotspot"
                        ? "Hotspot"
                        : "—"
            );
        }

        setText(
            "network-security",
            network.security ||
                (
                    connectionType === "ethernet"
                        ? "Ethernet"
                        : connectionType === "hotspot"
                            ? "WPA2 hotspot"
                            : "—"
                )
        );

        setText(
            "network-gateway",
            network.gateway ||
                ethernet.gateway ||
                wifi.gateway ||
                "—"
        );

        setText(
            "network-interface",
            network.interface ||
                ethernet.interface ||
                network.wifi_interface ||
                wifi.interface ||
                "Not detected"
        );

        disconnectButton.disabled =
            requestRunning ||
            !wifiConnected;

        hotspotStartButton.disabled =
            requestRunning ||
            !wifiAvailable ||
            hotspotActive;

        hotspotStopButton.disabled =
            requestRunning ||
            !hotspotActive;

        if (network.wifi_scan_blocked_reason) {
            scanButton.title = network.wifi_scan_blocked_reason;
        } else {
            scanButton.title = "";
        }

        statusNote.textContent =
            `Updated · ${new Date().toLocaleTimeString(
                [],
                {
                    hour: "numeric",
                    minute: "2-digit"
                }
            )}`;
    }

    function signalIcon(signal) {
        const wrapper = document.createElement("span");
        wrapper.className = "network-signal";
        wrapper.title = `${signal}% signal`;

        const activeBars =
            signal >= 80
                ? 4
                : signal >= 55
                  ? 3
                  : signal >= 30
                    ? 2
                    : signal > 0
                      ? 1
                      : 0;

        for (let index = 1; index <= 4; index += 1) {
            const bar = document.createElement("span");

            if (index <= activeBars) {
                bar.className = "active";
            }

            wrapper.appendChild(bar);
        }

        return wrapper;
    }

    function createWifiRow(network) {
        const row = document.createElement("div");
        row.className = "network-row";

        const copy = document.createElement("div");
        copy.className = "network-row-copy";

        const title = document.createElement("div");
        title.className = "network-row-title";

        title.appendChild(signalIcon(network.signal || 0));

        const titleText = document.createElement("span");
        titleText.className = "network-row-title-text";
        titleText.textContent = network.ssid;

        title.appendChild(titleText);

        if (network.connected) {
            const badge = document.createElement("span");
            badge.className = "network-badge";
            badge.textContent = "Connected";
            title.appendChild(badge);
        }

        const meta = document.createElement("div");
        meta.className = "network-row-meta";

        const security =
            network.security &&
            network.security !== "--"
                ? network.security
                : "Open network";

        meta.textContent =
            `${network.signal || 0}% signal · ${security}`;

        copy.append(title, meta);

        const actions = document.createElement("div");
        actions.className = "network-row-actions";

        const connectButton = createButton(
            network.connected ? "Connected" : "Connect",
            network.connected ? "" : "primary"
        );

        connectButton.disabled =
            network.connected || requestRunning;

        connectButton.addEventListener(
            "click",
            () => openConnectDialog(network)
        );

        actions.appendChild(connectButton);
        row.append(copy, actions);

        return row;
    }

    function renderWifiNetworks(networks, emptyMessage) {
        wifiList.replaceChildren();

        if (!Array.isArray(networks) || !networks.length) {
            wifiList.innerHTML =
                `<div class="network-empty">${
                    emptyMessage ||
                    "No nearby Wi-Fi networks were found."
                }</div>`;

            return;
        }

        for (const network of networks) {
            wifiList.appendChild(createWifiRow(network));
        }
    }

    function renderSavedNetworks(connections) {
        savedList.replaceChildren();

        if (
            !Array.isArray(connections) ||
            !connections.length
        ) {
            savedList.innerHTML =
                '<div class="network-empty">No saved Wi-Fi networks.</div>';

            return;
        }

        for (const connection of connections) {
            const row = document.createElement("div");
            row.className = "network-row";

            const copy = document.createElement("div");
            copy.className = "network-row-copy";

            const title = document.createElement("div");
            title.className = "network-row-title";

            const titleText =
                document.createElement("span");

            titleText.className =
                "network-row-title-text";

            titleText.textContent = connection.name;
            title.appendChild(titleText);

            if (connection.active) {
                const badge = document.createElement("span");
                badge.className = "network-badge";
                badge.textContent = "Active";
                title.appendChild(badge);
            }

            const meta = document.createElement("div");
            meta.className = "network-row-meta";
            meta.textContent = connection.autoconnect
                ? "Connects automatically"
                : "Manual connection";

            copy.append(title, meta);

            const actions = document.createElement("div");
            actions.className = "network-row-actions";

            const forgetButton = createButton(
                "Forget",
                "danger"
            );

            forgetButton.disabled =
                requestRunning || connection.active;

            forgetButton.addEventListener(
                "click",
                () => forgetNetwork(connection.name)
            );

            actions.appendChild(forgetButton);
            row.append(copy, actions);
            savedList.appendChild(row);
        }
    }

    function closeDialog(dialog) {
        dialog.remove();
    }

    function openConnectDialog(network) {
        const backdrop = document.createElement("div");
        backdrop.className = "network-dialog-backdrop";

        const dialog = document.createElement("form");
        dialog.className = "network-dialog";

        const heading = document.createElement("h3");
        heading.textContent = `Connect to ${network.ssid}`;

        const description =
            document.createElement("p");

        description.className =
            "network-dialog-description";

        description.textContent = network.secured
            ? "Enter the Wi-Fi password. MineBox may disconnect from its current network while switching."
            : "This appears to be an open Wi-Fi network.";

        const passwordField =
            document.createElement("label");

        passwordField.className = "network-field";

        const passwordLabel =
            document.createElement("span");

        passwordLabel.className = "network-field-label";
        passwordLabel.textContent = "Wi-Fi password";

        const passwordInput =
            document.createElement("input");

        passwordInput.className = "network-input";
        passwordInput.type = "password";
        passwordInput.autocomplete =
            "current-password";

        if (network.secured) {
            passwordInput.required = true;
            passwordInput.minLength = 8;
            passwordInput.maxLength = 64;
        } else {
            passwordInput.placeholder =
                "No password required";
            passwordInput.disabled = true;
        }

        passwordField.append(
            passwordLabel,
            passwordInput
        );

        const actions = document.createElement("div");
        actions.className = "network-dialog-actions";

        const cancelButton = createButton("Cancel");

        cancelButton.addEventListener(
            "click",
            () => closeDialog(backdrop)
        );

        const connectButton = createButton(
            "Connect",
            "primary"
        );

        connectButton.type = "submit";

        actions.append(cancelButton, connectButton);

        dialog.append(
            heading,
            description,
            passwordField,
            actions
        );

        dialog.addEventListener(
            "submit",
            async event => {
                event.preventDefault();

                closeDialog(backdrop);

                await connectWifi(
                    network.ssid,
                    network.secured
                        ? passwordInput.value
                        : ""
                );
            }
        );

        backdrop.addEventListener(
            "click",
            event => {
                if (event.target === backdrop) {
                    closeDialog(backdrop);
                }
            }
        );

        backdrop.appendChild(dialog);
        document.body.appendChild(backdrop);

        if (network.secured) {
            passwordInput.focus();
        } else {
            connectButton.focus();
        }
    }

    async function loadStatus(showErrors = true) {
        try {
            const response = await fetch(
                `${API_BASE}/status`,
                {
                    method: "GET",
                    cache: "no-store"
                }
            );

            const data = await parseResponse(response);
            updateStatus(data.network || {});
        } catch (error) {
            statusNote.textContent = "Network status unavailable";

            if (showErrors) {
                showMessage(
                    error.message ||
                        "MineBox could not load network status.",
                    "error"
                );
            }
        }
    }

    async function loadWifiNetworks(rescan = false) {
        if (requestRunning) {
            return;
        }

        scanButton.disabled = true;
        scanButton.textContent = rescan
            ? "Scanning…"
            : "Loading…";

        wifiList.innerHTML =
            '<div class="network-empty">Scanning for Wi-Fi networks…</div>';

        try {
            const response = await fetch(
                `${API_BASE}/wifi?rescan=${
                    rescan ? "true" : "false"
                }`,
                {
                    method: "GET",
                    cache: "no-store"
                }
            );

            const data = await parseResponse(response);
            renderWifiNetworks(
                data.networks || [],
                data.message || "No nearby Wi-Fi networks were found."
            );
        } catch (error) {
            wifiList.innerHTML =
                `<div class="network-empty">${
                    error.message ||
                    "Wi-Fi scanning is unavailable."
                }</div>`;
        } finally {
            scanButton.disabled = requestRunning;
            scanButton.textContent = "Scan Networks";
        }
    }

    async function loadSavedNetworks() {
        try {
            const response = await fetch(
                `${API_BASE}/saved`,
                {
                    method: "GET",
                    cache: "no-store"
                }
            );

            const data = await parseResponse(response);
            renderSavedNetworks(
                data.connections || []
            );
        } catch (error) {
            savedList.innerHTML =
                `<div class="network-empty">${
                    error.message ||
                    "Saved networks are unavailable."
                }</div>`;
        }
    }

    async function connectWifi(ssid, password) {
        if (requestRunning) {
            return;
        }

        setBusy(true);
        clearMessage();

        showMessage(
            `Connecting MineBox to ${ssid}…`,
            "warning"
        );

        try {
            const response = await fetch(
                `${API_BASE}/connect`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        ssid,
                        password,
                        hidden: false
                    })
                }
            );

            const data = await parseResponse(response);

            showMessage(
                data.message ||
                    `MineBox connected to ${ssid}.`,
                "success"
            );
        } catch (error) {
            showMessage(
                error.message ||
                    `MineBox could not connect to ${ssid}.`,
                "error"
            );
        } finally {
            setBusy(false);
            await refreshEverything(false);
        }
    }

    async function disconnectWifi() {
        if (
            requestRunning ||
            !window.confirm(
                "Disconnect MineBox from its current Wi-Fi network?"
            )
        ) {
            return;
        }

        setBusy(true);
        clearMessage();

        try {
            const response = await fetch(
                `${API_BASE}/disconnect`,
                {
                    method: "POST"
                }
            );

            const data = await parseResponse(response);

            showMessage(
                data.message || "Wi-Fi disconnected.",
                "success"
            );
        } catch (error) {
            showMessage(
                error.message ||
                    "MineBox could not disconnect Wi-Fi.",
                "error"
            );
        } finally {
            setBusy(false);
            await refreshEverything(false);
        }
    }

    async function forgetNetwork(connectionName) {
        if (
            requestRunning ||
            !window.confirm(
                `Forget the saved network "${connectionName}"?`
            )
        ) {
            return;
        }

        setBusy(true);
        clearMessage();

        try {
            const response = await fetch(
                `${API_BASE}/forget`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        connection_name: connectionName
                    })
                }
            );

            const data = await parseResponse(response);

            showMessage(
                data.message ||
                    `Forgot ${connectionName}.`,
                "success"
            );
        } catch (error) {
            showMessage(
                error.message ||
                    `MineBox could not forget ${connectionName}.`,
                "error"
            );
        } finally {
            setBusy(false);
            await loadSavedNetworks();
        }
    }

    async function startHotspot(event) {
        event.preventDefault();

        if (
            requestRunning ||
            !event.currentTarget.checkValidity()
        ) {
            event.currentTarget.reportValidity();
            return;
        }

        setBusy(true);
        clearMessage();

        showMessage(
            "Starting the MineBox setup hotspot…",
            "warning"
        );

        try {
            const response = await fetch(
                `${API_BASE}/hotspot/start`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        ssid: hotspotSsidInput.value.trim(),
                        password:
                            hotspotPasswordInput.value
                    })
                }
            );

            const data = await parseResponse(response);

            hotspotPasswordInput.value = "";

            showMessage(
                data.message ||
                    "MineBox setup hotspot started.",
                "success"
            );
        } catch (error) {
            showMessage(
                error.message ||
                    "MineBox could not start the hotspot.",
                "error"
            );
        } finally {
            setBusy(false);
            await refreshEverything(false);
        }
    }

    async function stopHotspot() {
        if (
            requestRunning ||
            !window.confirm(
                "Stop the MineBox setup hotspot?"
            )
        ) {
            return;
        }

        setBusy(true);
        clearMessage();

        try {
            const response = await fetch(
                `${API_BASE}/hotspot/stop`,
                {
                    method: "POST"
                }
            );

            const data = await parseResponse(response);

            showMessage(
                data.message ||
                    "MineBox setup hotspot stopped.",
                "success"
            );
        } catch (error) {
            showMessage(
                error.message ||
                    "MineBox could not stop the hotspot.",
                "error"
            );
        } finally {
            setBusy(false);
            await refreshEverything(false);
        }
    }

    async function refreshEverything(showStatus = true) {
        if (requestRunning) {
            return;
        }

        refreshButton.disabled = true;
        refreshButton.textContent = "Refreshing…";

        if (showStatus) {
            clearMessage();
        }

        await loadStatus(showStatus);

        await Promise.all([
            loadWifiNetworks(false),
            loadSavedNetworks()
        ]);

        refreshButton.disabled = false;
        refreshButton.textContent = "Refresh";
    }

    function setActiveNavigation() {
        const links =
            document.querySelectorAll(".nav-item");

        function update() {
            const hash = window.location.hash;

            for (const link of links) {
                if (
                    link.id === "network-nav-item" &&
                    hash === "#network"
                ) {
                    link.classList.add("active");
                } else if (
                    hash === "#network" &&
                    link.getAttribute("href") === "/"
                ) {
                    link.classList.remove("active");
                } else if (
                    link.id === "network-nav-item"
                ) {
                    link.classList.remove("active");
                }
            }
        }

        window.addEventListener("hashchange", update);
        update();
    }

    async function initialize() {
        injectStyles();

        /*
         * settings.js may create its panel after this script starts,
         * so retry briefly until a safe insertion point exists.
         */
        let attempts = 0;

        const tryInjection = async () => {
            injectNavigation();

            if (!injectPanel()) {
                attempts += 1;

                if (attempts < 30) {
                    window.setTimeout(
                        tryInjection,
                        100
                    );
                }

                return;
            }

            setActiveNavigation();
            await refreshEverything(false);

            refreshTimer = window.setInterval(
                () => {
                    if (
                        !document.hidden &&
                        !requestRunning
                    ) {
                        loadStatus(false);
                    }
                },
                15000
            );
        };

        await tryInjection();
    }

    document.addEventListener(
        "DOMContentLoaded",
        initialize
    );

    window.addEventListener(
        "beforeunload",
        () => {
            if (refreshTimer) {
                window.clearInterval(refreshTimer);
            }
        }
    );
})();
