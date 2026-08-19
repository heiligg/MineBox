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
    let dnsSlugInput;
    let dnsTokenInput;
    let dnsClaimButton;
    let dnsClearButton;
    let playitEnableButton;
    let playitDisableButton;
    let playitHelp;
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
            .join-forward {
                margin-top: 20px;
                padding: 16px;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 14px;
                background: rgba(255,255,255,0.03);
            }
            .join-forward-title {
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                margin-bottom: 6px;
            }
            .join-forward-help {
                color: var(--muted);
                font-size: 13px;
                line-height: 1.45;
                margin-bottom: 12px;
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
            .join-dns {
                margin-top: 18px;
                padding-top: 16px;
                border-top: 1px solid rgba(255,255,255,0.08);
            }
            .join-dns-title {
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                margin-bottom: 6px;
            }
            .join-dns-help {
                color: var(--muted);
                font-size: 13px;
                line-height: 1.45;
                margin-bottom: 12px;
            }
            .join-dns-help a { color: #9ec1ff; }
            .join-dns-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 8px;
                margin-bottom: 10px;
            }
            .join-dns-prefix {
                font-weight: 800;
                font-size: 16px;
            }
            .join-dns-input {
                min-width: 140px;
                flex: 1;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                font: inherit;
                font-weight: 700;
                padding: 10px 12px;
            }
            .join-dns-suffix {
                color: var(--muted);
                font-weight: 700;
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

    function bindExisting() {
        panel = document.getElementById("join");
        if (!panel) {
            return false;
        }

        note = document.getElementById("join-refresh-note") || note;
        lanValue = document.getElementById("join-lan-value");
        lanIpValue = document.getElementById("join-lan-ip-value");
        internetValue = document.getElementById("join-internet-value");
        statusValue = document.getElementById("join-status-value");
        message = document.getElementById("join-message");
        refreshButton = document.getElementById("join-refresh-button");
        enableButton = document.getElementById("join-enable-button");
        disableButton = document.getElementById("join-disable-button");
        dnsSlugInput = document.getElementById("join-dns-slug");
        dnsTokenInput = document.getElementById("join-dns-token");
        dnsClaimButton = document.getElementById("join-dns-claim");
        dnsClearButton = document.getElementById("join-dns-clear");
        playitEnableButton = document.getElementById("join-playit-enable");
        playitDisableButton = document.getElementById("join-playit-disable");
        playitHelp = document.getElementById("join-playit-help");

        if (!lanValue || !refreshButton || !dnsClaimButton || !playitEnableButton) {
            return false;
        }

        if (panel.dataset.joinBound === "1") {
            return true;
        }

        refreshButton.addEventListener("click", () => loadStatus(true));
        enableButton.addEventListener("click", enableInternet);
        disableButton.addEventListener("click", disableInternet);
        dnsClaimButton.addEventListener("click", claimDns);
        dnsClearButton.addEventListener("click", clearDns);
        playitEnableButton.addEventListener("click", enablePlayit);
        playitDisableButton.addEventListener("click", disablePlayit);
        panel.dataset.joinBound = "1";
        return true;
    }

    function injectPanel() {
        if (bindExisting()) {
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
        panel.innerHTML = `
            <div class="section-header">
                <div>
                    <h2 class="section-title">How to join</h2>
                    <span class="section-note" id="join-refresh-note">Loading join addresses…</span>
                </div>
            </div>
            <div class="join-grid">
                <div class="join-row">
                    <span class="join-label">Home network (best)</span>
                    <strong class="join-value" id="join-lan-value">…</strong>
                </div>
                <div class="join-row">
                    <span class="join-label">Home network IP</span>
                    <strong class="join-value" id="join-lan-ip-value">…</strong>
                </div>
            </div>
            <div class="join-notes" id="join-notes"></div>
            <div class="join-forward" id="join-forward">
                <div class="join-forward-title">Port forwarding</div>
                <div class="join-forward-help">
                    Opens Minecraft to the internet, then lets you pick a public
                    <strong>minebox-</strong> name for friends to type.
                </div>
                <div class="join-grid">
                    <div class="join-row">
                        <span class="join-label">Internet address</span>
                        <strong class="join-value" id="join-internet-value">…</strong>
                    </div>
                    <div class="join-row">
                        <span class="join-label">Port forward</span>
                        <strong class="join-value" id="join-status-value">…</strong>
                    </div>
                </div>
                <div class="join-actions">
                    <button type="button" class="join-button" id="join-refresh-button">Refresh</button>
                    <button type="button" class="join-button primary" id="join-playit-enable">Easy internet join (playit.gg)</button>
                    <button type="button" class="join-button" id="join-playit-disable">Stop playit.gg</button>
                    <button type="button" class="join-button" id="join-enable-button">Enable port forwarding</button>
                    <button type="button" class="join-button" id="join-disable-button">Disable port forwarding</button>
                </div>
                <div class="join-dns-help" id="join-playit-help">
                    playit.gg is the easy path: no router settings. After you click the button, open the claim link once if it appears.
                </div>
                <div class="join-dns">
                    <div class="join-dns-title">Public name</div>
                    <div class="join-dns-help">
                        Always starts with <strong>minebox-</strong>. Type the rest and claim it here.
                        If that name is taken, pick another word.
                    </div>
                    <div class="join-dns-row">
                        <span class="join-dns-prefix">minebox-</span>
                        <input type="text" class="join-dns-input" id="join-dns-slug" placeholder="yourword" autocomplete="off" spellcheck="false">
                        <span class="join-dns-suffix">.duckdns.org</span>
                    </div>
                    <div class="join-dns-row">
                        <input type="password" class="join-dns-input" id="join-dns-token" placeholder="DuckDNS token (saved on this MineBox)" autocomplete="off">
                    </div>
                    <div class="join-actions">
                        <button type="button" class="join-button primary" id="join-dns-claim">Claim name</button>
                        <button type="button" class="join-button" id="join-dns-clear">Clear name</button>
                    </div>
                </div>
                <div class="join-message" id="join-message"></div>
            </div>
        `;
        target.parentNode.insertBefore(panel, target.nextSibling);
        return bindExisting();
    }

    function showMessage(text, type) {
        message.textContent = text || "";
        message.className = text
            ? `join-message visible ${type || ""}`.trim()
            : "join-message";
    }

    function setBusy(state) {
        busy = state;
        [refreshButton, enableButton, disableButton, dnsClaimButton, dnsClearButton, playitEnableButton, playitDisableButton]
            .filter(Boolean)
            .forEach((button) => {
                button.disabled = state;
            });
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

        const dns = data.public_dns || {};
        if (dnsSlugInput && !dnsSlugInput.matches(":focus")) {
            dnsSlugInput.value = dns.slug || dnsSlugInput.value || "";
        }
        if (dnsTokenInput && dns.token_set) {
            dnsTokenInput.placeholder = "Token saved — paste a new one only to change it";
        }

        if (data.playit && data.playit.address) {
            statusValue.textContent = "playit.gg connected";
            statusValue.className = "join-value ok";
        } else if (data.playit && data.playit.claim_url) {
            statusValue.textContent = "playit.gg needs claim link";
            statusValue.className = "join-value warn";
        } else if (data.playit && data.playit.running) {
            statusValue.textContent = "playit.gg starting";
            statusValue.className = "join-value warn";
        } else if (data.internet_mapped && data.internet_reachable) {
            statusValue.textContent = "Port forwarded";
            statusValue.className = "join-value ok";
        } else if (data.internet_mapped && data.upnp && data.upnp.double_nat) {
            statusValue.textContent = "Router forwarded (double NAT)";
            statusValue.className = "join-value warn";
        } else if (data.internet_address) {
            statusValue.textContent = "Needs router port forward";
            statusValue.className = "join-value warn";
        } else {
            statusValue.textContent = "No public IP detected";
            statusValue.className = "join-value warn";
        }

        const notes = document.getElementById("join-notes");
        if (notes) {
            notes.replaceChildren();
            for (const line of data.notes || []) {
                const p = document.createElement("div");
                p.textContent = line;
                notes.appendChild(p);
            }
        }

        if (playitHelp) {
            const playit = data.playit || {};
            if (playit.claim_url) {
                playitHelp.innerHTML =
                    'Open this claim link once: <a href="' +
                    playit.claim_url +
                    '" target="_blank" rel="noopener">' +
                    playit.claim_url +
                    "</a>";
            } else if (playit.address) {
                playitHelp.textContent =
                    "playit.gg is live. Friends join with " + playit.address + ".";
            } else {
                playitHelp.textContent =
                    "playit.gg is the easy path: no router settings. After you click the button, open the claim link once if it appears.";
            }
        }

        if (note) {
            note.textContent =
                `Updated · ${new Date().toLocaleTimeString([], {
                    hour: "numeric",
                    minute: "2-digit"
                })}`;
        }
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
                data.message || "Port forwarding enabled.",
                data.join && data.join.internet_reachable ? "success" : "warning"
            );
        } catch (error) {
            showMessage(
                error.message ||
                "Could not enable automatic port forwarding.",
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
                data.message || "Port forwarding disabled.",
                "success"
            );
        } catch (error) {
            showMessage(
                error.message || "Could not disable port forwarding.",
                "error"
            );
        } finally {
            setBusy(false);
        }
    }

    async function claimDns() {
        if (busy) {
            return;
        }

        setBusy(true);
        showMessage("Checking if that MineBox name is free…", "warning");
        try {
            const response = await fetch(`${API_BASE}/dns/claim`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slug: (dnsSlugInput && dnsSlugInput.value) || "",
                    token: (dnsTokenInput && dnsTokenInput.value) || ""
                })
            });
            const data = await parseResponse(response);
            if (data.join) {
                render(data.join);
            }
            if (dnsTokenInput) {
                dnsTokenInput.value = "";
            }
            showMessage(
                data.message || "Public MineBox name claimed.",
                "success"
            );
        } catch (error) {
            showMessage(
                error.message || "Could not claim that public name.",
                "error"
            );
        } finally {
            setBusy(false);
        }
    }

    async function clearDns() {
        if (busy) {
            return;
        }

        setBusy(true);
        try {
            const response = await fetch(`${API_BASE}/dns/clear`, {
                method: "POST"
            });
            const data = await parseResponse(response);
            if (data.join) {
                render(data.join);
            }
            if (dnsSlugInput) {
                dnsSlugInput.value = "";
            }
            showMessage(data.message || "Public name cleared.", "success");
        } catch (error) {
            showMessage(
                error.message || "Could not clear the public name.",
                "error"
            );
        } finally {
            setBusy(false);
        }
    }

    async function enablePlayit() {
        if (busy) {
            return;
        }

        setBusy(true);
        showMessage("Starting playit.gg… this can take a minute the first time.", "warning");
        try {
            const response = await fetch(`${API_BASE}/playit/enable`, {
                method: "POST"
            });
            const data = await parseResponse(response);
            if (data.join) {
                render(data.join);
            }
            const playit = (data.join && data.join.playit) || {};
            showMessage(
                data.message || playit.message || "playit.gg started.",
                playit.address ? "success" : "warning"
            );
        } catch (error) {
            showMessage(
                error.message || "Could not start playit.gg.",
                "error"
            );
        } finally {
            setBusy(false);
        }
    }

    async function disablePlayit() {
        if (busy) {
            return;
        }

        setBusy(true);
        try {
            const response = await fetch(`${API_BASE}/playit/disable`, {
                method: "POST"
            });
            const data = await parseResponse(response);
            if (data.join) {
                render(data.join);
            }
            showMessage(data.message || "playit.gg stopped.", "success");
        } catch (error) {
            showMessage(
                error.message || "Could not stop playit.gg.",
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
        if (window.location.hash === "#join" && panel) {
            window.setTimeout(() => {
                panel.scrollIntoView({ behavior: "smooth", block: "start" });
            }, 50);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
