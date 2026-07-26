"use strict";

(() => {
    const STATUS_API = "/api/v1/auth/status";
    const DISMISS_API = "/api/v1/auth/security-reminder/dismiss";
    const CHANGE_API = "/api/v1/auth/change-password";

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
            .security-panel button {
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
            .security-panel input {
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
        `;
        document.head.appendChild(style);
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
                <button type="button" id="security-change-toggle">Change admin password</button>
                <button type="button" id="security-dismiss">Dismiss</button>
            </div>
            <div class="security-panel" id="security-change-panel">
                <input type="password" id="security-current" placeholder="Current password" autocomplete="current-password" />
                <input type="password" id="security-new" placeholder="New password (12+ chars)" autocomplete="new-password" minlength="12" />
                <input type="password" id="security-confirm" placeholder="Confirm new password" autocomplete="new-password" minlength="12" />
                <button type="button" id="security-change-save">Save new password</button>
                <div class="security-note" id="security-change-note"></div>
                <hr style="border:0;border-top:1px solid rgba(255,255,255,0.1);margin:14px 0;" />
                <div class="security-note" id="security-tls-status">Checking HTTPS…</div>
                <div class="security-reminder-actions">
                    <button type="button" id="security-tls-enable">Enable HTTPS</button>
                    <button type="button" id="security-tls-disable">Use HTTP</button>
                </div>
                <div class="security-note" id="security-tls-note"></div>
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

    function wire() {
        injectStyles();
        const banner = ensureBanner();
        if (!banner) {
            window.setTimeout(wire, 250);
            return;
        }

        const toggle = document.getElementById("security-change-toggle");
        const panel = document.getElementById("security-change-panel");
        const dismiss = document.getElementById("security-dismiss");
        const save = document.getElementById("security-change-save");
        const note = document.getElementById("security-change-note");

        if (toggle && panel) {
            toggle.addEventListener("click", () => {
                panel.classList.toggle("visible");
            });
        }

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
                banner.hidden = true;
            });
        }

        if (save) {
            save.addEventListener("click", async () => {
                const current = document.getElementById("security-current");
                const next = document.getElementById("security-new");
                const confirm = document.getElementById("security-confirm");
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
                } catch (error) {
                    note.textContent = error.message || "Could not change password.";
                }
            });
        }

        async function refreshTls() {
            const status = document.getElementById("security-tls-status");
            if (!status) {
                return;
            }
            try {
                const response = await fetch("/api/v1/security/tls", {
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
                    enable
                        ? "/api/v1/security/tls/enable"
                        : "/api/v1/security/tls/disable",
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
