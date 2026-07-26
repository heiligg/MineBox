"use strict";

(() => {
    const STATUS_API = "/api/v1/auth/status";
    const DISMISS_API = "/api/v1/auth/security-reminder/dismiss";
    const CHANGE_API = "/api/v1/auth/change-password";
    const TLS_API = "/api/v1/security/tls";

    function injectStyles() {
        if (document.getElementById("minebox-security-styles")) {
            return;
        }
        const style = document.createElement("style");
        style.id = "minebox-security-styles";
        style.textContent = `
            .security-reminder {
                margin: 0 0 16px;
                padding: 14px 16px;
                border-radius: 12px;
                border: 1px solid rgba(255, 180, 60, 0.28);
                background: rgba(255, 180, 60, 0.1);
                color: #ffd27a;
            }
            .security-reminder[hidden] { display: none; }
            .security-reminder-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 10px;
            }
            .security-reminder button,
            .security-panel button,
            .security-section button {
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 8px 12px;
            }
            .security-panel {
                margin-top: 12px;
                display: none;
                gap: 8px;
            }
            .security-panel.visible {
                display: grid;
            }
            .security-panel input,
            .security-section input {
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(0,0,0,0.25);
                color: var(--text);
                font: inherit;
                padding: 10px 12px;
            }
            .security-note {
                margin-top: 8px;
                font-size: 13px;
                color: var(--muted);
            }
            .security-section {
                display: grid;
                gap: 12px;
                margin-top: 16px;
            }
            .security-section h3 {
                margin: 0;
                color: var(--muted);
                font-size: 13px;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .security-section-copy {
                color: var(--muted);
                font-size: 14px;
                line-height: 1.45;
            }
            .security-password-grid {
                display: grid;
                gap: 8px;
                max-width: 420px;
            }
        `;
        document.head.appendChild(style);
    }

    function injectNav() {
        const nav = document.querySelector(".sidebar-nav, nav, .nav");
        if (!nav || document.getElementById("security-nav-item")) {
            return;
        }
        const link = document.createElement("a");
        link.id = "security-nav-item";
        link.className = "nav-item";
        link.href = "#security";
        link.innerHTML = `
            <span class="nav-icon" aria-hidden="true">⊘</span>
            <span class="nav-text">Security</span>
        `;
        const settingsLink = [...nav.querySelectorAll(".nav-item")].find(
            (item) => item.getAttribute("href") === "#settings"
                || item.textContent.trim().includes("Settings")
        );
        if (settingsLink) {
            nav.insertBefore(link, settingsLink.nextSibling);
        } else {
            nav.appendChild(link);
        }
    }

    function injectPanel() {
        if (document.getElementById("security")) {
            return true;
        }
        const settings = document.getElementById("settings");
        const backups = document.getElementById("backups");
        const target = settings || backups;
        if (!target || !target.parentNode) {
            return false;
        }
        const panel = document.createElement("article");
        panel.id = "security";
        panel.className = "panel section";
        panel.innerHTML = `
            <div class="section-header">
                <div>
                    <h2 class="section-title">Security</h2>
                    <span class="section-note">Admin password and dashboard HTTPS</span>
                </div>
            </div>
            <div class="security-section">
                <h3>Admin password</h3>
                <p class="security-section-copy">
                    Change the dashboard password. Use at least 12 characters.
                </p>
                <div class="security-password-grid">
                    <input type="password" id="security-page-current" placeholder="Current password" autocomplete="current-password" />
                    <input type="password" id="security-page-new" placeholder="New password (12+ chars)" autocomplete="new-password" minlength="12" />
                    <input type="password" id="security-page-confirm" placeholder="Confirm new password" autocomplete="new-password" minlength="12" />
                    <button type="button" id="security-page-save">Save new password</button>
                    <div class="security-note" id="security-page-note"></div>
                </div>
            </div>
            <div class="security-section">
                <h3>Dashboard HTTPS</h3>
                <p class="security-section-copy">
                    Enable a self-signed certificate on port 8080. Browsers will show a
                    warning until you trust the certificate. Useful on shared LANs.
                </p>
                <div class="security-note" id="security-tls-status">Checking HTTPS…</div>
                <div class="security-reminder-actions">
                    <button type="button" id="security-tls-enable">Enable HTTPS</button>
                    <button type="button" id="security-tls-disable">Use HTTP</button>
                </div>
                <div class="security-note" id="security-tls-note"></div>
            </div>
        `;
        target.parentNode.insertBefore(panel, target.nextSibling);
        return true;
    }

    function ensureBanner() {
        let banner = document.getElementById("security-reminder");
        if (banner) {
            return banner;
        }
        const alerts = document.getElementById("system-alerts");
        const hero = document.querySelector(".hero");
        const anchor = alerts || hero;
        if (!anchor || !anchor.parentNode) {
            return null;
        }
        banner = document.createElement("div");
        banner.id = "security-reminder";
        banner.className = "security-reminder";
        banner.hidden = true;
        banner.innerHTML = `
            <strong>Security reminder</strong>
            <p id="security-reminder-text" style="margin:8px 0 0;"></p>
            <div class="security-reminder-actions">
                <a class="nav-item" href="#security" id="security-reminder-open" style="text-decoration:none;padding:8px 12px;border:1px solid rgba(255,255,255,0.12);border-radius:10px;background:rgba(255,255,255,0.04);color:var(--text);font-weight:700;">Open Security</a>
                <button type="button" id="security-dismiss">Dismiss</button>
            </div>
        `;
        anchor.parentNode.insertBefore(banner, anchor);
        return banner;
    }

    async function loadReminder() {
        const banner = ensureBanner();
        if (!banner) {
            return;
        }
        try {
            const response = await fetch(STATUS_API, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const payload = await response.json().catch(() => ({}));
            const reminder = payload.security_reminder || {};
            if (!payload.authenticated || !reminder.show_reminder) {
                banner.hidden = true;
                return;
            }
            const text = document.getElementById("security-reminder-text");
            if (text) {
                text.textContent =
                    reminder.message
                    || "Change default passwords before exposing this device.";
            }
            banner.hidden = false;
        } catch (_error) {
            banner.hidden = true;
        }
    }

    async function refreshTls() {
        const status = document.getElementById("security-tls-status");
        if (!status) {
            return;
        }
        try {
            const response = await fetch(TLS_API, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                status.textContent = "HTTPS status unavailable.";
                return;
            }
            status.textContent = payload.message
                || (payload.enabled
                    ? "HTTPS is enabled (self-signed certificate)."
                    : "Dashboard is using HTTP.");
        } catch (_error) {
            status.textContent = "HTTPS status unavailable.";
        }
    }

    async function setTls(enable) {
        const tlsNote = document.getElementById("security-tls-note");
        if (tlsNote) {
            tlsNote.textContent = enable
                ? "Enabling HTTPS and restarting the API…"
                : "Switching back to HTTP…";
        }
        try {
            const response = await fetch(
                enable ? `${TLS_API}/enable` : `${TLS_API}/disable`,
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { Accept: "application/json" },
                }
            );
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || "TLS update failed.");
            }
            if (tlsNote) {
                tlsNote.textContent = enable
                    ? "HTTPS enabled. Reload using https:// and trust the self-signed warning."
                    : "HTTP restored. Reload the dashboard.";
            }
            window.setTimeout(() => {
                const scheme = enable ? "https" : "http";
                window.location.href = `${scheme}://${window.location.host}/`;
            }, 1500);
        } catch (error) {
            if (tlsNote) {
                tlsNote.textContent = error.message || "TLS update failed.";
            }
        }
    }

    async function changePassword(currentId, newId, confirmId, noteId) {
        const current = document.getElementById(currentId);
        const next = document.getElementById(newId);
        const confirm = document.getElementById(confirmId);
        const note = document.getElementById(noteId);
        if (!current || !next || !confirm || !note) {
            return;
        }
        const body = new URLSearchParams({
            current_password: current.value || "",
            new_password: next.value || "",
            confirmation: confirm.value || "",
        });
        note.textContent = "Saving…";
        try {
            const response = await fetch(CHANGE_API, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body,
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || "Could not change password.");
            }
            note.textContent = "Password updated.";
            current.value = "";
            next.value = "";
            confirm.value = "";
            loadReminder();
        } catch (error) {
            note.textContent = error.message || "Could not change password.";
        }
    }

    function wire() {
        injectStyles();
        injectNav();
        if (!injectPanel()) {
            window.setTimeout(wire, 250);
            return;
        }
        ensureBanner();

        const dismiss = document.getElementById("security-dismiss");
        if (dismiss) {
            dismiss.addEventListener("click", async () => {
                try {
                    await fetch(DISMISS_API, {
                        method: "POST",
                        credentials: "same-origin",
                        headers: { Accept: "application/json" },
                    });
                } catch (_error) {
                    // ignore
                }
                const banner = document.getElementById("security-reminder");
                if (banner) {
                    banner.hidden = true;
                }
            });
        }

        const pageSave = document.getElementById("security-page-save");
        if (pageSave) {
            pageSave.addEventListener("click", () => changePassword(
                "security-page-current",
                "security-page-new",
                "security-page-confirm",
                "security-page-note"
            ));
        }

        const tlsEnable = document.getElementById("security-tls-enable");
        const tlsDisable = document.getElementById("security-tls-disable");
        if (tlsEnable) {
            tlsEnable.addEventListener("click", () => setTls(true));
        }
        if (tlsDisable) {
            tlsDisable.addEventListener("click", () => setTls(false));
        }

        loadReminder();
        refreshTls();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", wire);
    } else {
        wire();
    }
})();
