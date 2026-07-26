"use strict";

(() => {
    const API_BASE = "/api/v1/mods";

    let panel;
    let note;
    let message;
    let searchInput;
    let urlInput;
    let resultsBox;
    let installedBox;
    let providerSelect;
    let cfKeyInput;
    let provider = "modrinth";
    let busy = false;
    let context = {
        target_folder: "mods",
        loader: "vanilla",
        version: "",
        supports_modrinth: false,
        supports_curseforge: false,
        curseforge_configured: false,
    };

    function injectStyles() {
        if (document.getElementById("minebox-mods-styles")) {
            return;
        }
        const style = document.createElement("style");
        style.id = "minebox-mods-styles";
        style.textContent = `
            .mods-panel { scroll-margin-top: 24px; }
            .mods-toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 16px;
            }
            .mods-toolbar input {
                flex: 1 1 220px;
                min-width: 160px;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                font: inherit;
                padding: 10px 12px;
            }
            .mods-button {
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 10px 14px;
            }
            .mods-button.primary {
                background: #2f6fed;
                border-color: #2f6fed;
            }
            .mods-button:disabled { opacity: 0.5; cursor: not-allowed; }
            .mods-grid {
                display: grid;
                gap: 18px;
                margin-top: 18px;
            }
            @media (min-width: 960px) {
                .mods-grid { grid-template-columns: 1.4fr 1fr; }
            }
            .mods-section h3 {
                margin: 0 0 10px;
                color: var(--muted);
                font-size: 13px;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .mods-card {
                display: grid;
                gap: 8px;
                padding: 12px 0;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
            .mods-card:last-child { border-bottom: 0; }
            .mods-card-title {
                font-weight: 800;
                color: var(--text);
            }
            .mods-card-desc {
                color: var(--muted);
                font-size: 13px;
                line-height: 1.4;
            }
            .mods-card-meta {
                color: var(--muted);
                font-size: 12px;
            }
            .mods-row {
                display: flex;
                justify-content: space-between;
                gap: 10px;
                align-items: center;
                padding: 8px 0;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
            .mods-empty { color: var(--muted); font-size: 14px; }
            .mods-message {
                display: none;
                margin-top: 14px;
                padding: 12px 14px;
                border-radius: 10px;
                font-size: 14px;
            }
            .mods-message.visible { display: block; }
            .mods-message.success {
                background: rgba(80, 180, 100, 0.15);
                color: #8ee895;
            }
            .mods-message.error {
                background: rgba(220, 80, 80, 0.12);
                color: #ff9c9c;
            }
            .mods-message.warning {
                background: rgba(255, 180, 60, 0.12);
                color: #ffd27a;
            }
        `;
        document.head.appendChild(style);
    }

    function injectNav() {
        const nav = document.querySelector(".sidebar-nav, nav, .nav");
        if (!nav || document.getElementById("mods-nav-item")) {
            return;
        }
        const link = document.createElement("a");
        link.id = "mods-nav-item";
        link.className = "nav-item";
        link.href = "#mods";
        link.innerHTML = `
            <span class="nav-icon" aria-hidden="true">◆</span>
            <span class="nav-text">Mods</span>
        `;
        const filesLink = [...nav.querySelectorAll(".nav-item")].find(
            (item) => item.getAttribute("href") === "#files"
                || item.textContent.trim().includes("Files")
        );
        const playersLink = [...nav.querySelectorAll(".nav-item")].find(
            (item) => item.getAttribute("href") === "#players"
                || item.textContent.trim().includes("Players")
        );
        const anchor = filesLink || playersLink;
        if (anchor) {
            nav.insertBefore(link, anchor.nextSibling);
        } else {
            nav.appendChild(link);
        }
    }

    function showMessage(text, type = "") {
        message.textContent = text || "";
        message.className = `mods-message${text ? ` visible ${type}` : ""}`.trim();
    }

    function detail(payload) {
        if (!payload) {
            return "Request failed.";
        }
        if (typeof payload.detail === "string") {
            return payload.detail;
        }
        return payload.message || "Request failed.";
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
            throw new Error(detail(payload));
        }
        return payload;
    }

    function formatDownloads(value) {
        const n = Number(value) || 0;
        if (n >= 1_000_000) {
            return `${(n / 1_000_000).toFixed(1)}M`;
        }
        if (n >= 1_000) {
            return `${(n / 1_000).toFixed(1)}K`;
        }
        return String(n);
    }

    function applyContext(payload) {
        context = {
            target_folder: payload.target_folder || "mods",
            loader: payload.loader || "vanilla",
            version: payload.version || "",
            supports_modrinth: Boolean(payload.supports_modrinth),
            supports_curseforge: Boolean(payload.supports_curseforge),
            curseforge_configured: Boolean(payload.curseforge_configured),
        };
        note.textContent = `${context.loader} ${context.version} → ${context.target_folder}/`;
        if (providerSelect) {
            providerSelect.value = provider;
        }
        if (cfKeyInput) {
            cfKeyInput.placeholder = context.curseforge_configured
                ? "CurseForge API key saved (paste to replace)"
                : "Paste CurseForge API key (console.curseforge.com)";
        }
        renderInstalled(payload.installed || []);
    }

    function renderInstalled(items) {
        installedBox.innerHTML = "";
        if (!items.length) {
            const empty = document.createElement("div");
            empty.className = "mods-empty";
            empty.textContent = `No jars in ${context.target_folder}/ yet.`;
            installedBox.appendChild(empty);
            return;
        }
        for (const item of items) {
            const row = document.createElement("div");
            row.className = "mods-row";
            const name = document.createElement("strong");
            name.textContent = item.name;
            const meta = document.createElement("span");
            meta.className = "mods-card-meta";
            meta.textContent = item.path;
            row.append(name, meta);
            installedBox.appendChild(row);
        }
    }

    function renderResults(items) {
        resultsBox.innerHTML = "";
        if (!items.length) {
            const empty = document.createElement("div");
            empty.className = "mods-empty";
            empty.textContent = provider === "curseforge"
                ? "No CurseForge results."
                : "No Modrinth results.";
            resultsBox.appendChild(empty);
            return;
        }
        for (const item of items) {
            const card = document.createElement("div");
            card.className = "mods-card";
            const title = document.createElement("div");
            title.className = "mods-card-title";
            title.textContent = item.title;
            const desc = document.createElement("div");
            desc.className = "mods-card-desc";
            desc.textContent = item.description || "";
            const meta = document.createElement("div");
            meta.className = "mods-card-meta";
            meta.textContent = `${formatDownloads(item.downloads)} downloads · ${
                (item.categories || []).slice(0, 4).join(", ") || item.project_type || "mod"
            }`;
            const button = document.createElement("button");
            button.type = "button";
            button.className = "mods-button primary";
            button.textContent = `Install to ${context.target_folder}/`;
            button.addEventListener("click", () => installProject(
                item.project_id || item.slug,
                item.provider || provider
            ));
            card.append(title, desc, meta, button);
            resultsBox.appendChild(card);
        }
    }

    async function loadContext() {
        const payload = await api(API_BASE);
        applyContext(payload);
        if (!payload.supports_modrinth && !payload.supports_curseforge) {
            showMessage(
                "This server type has limited catalog filtering. You can still paste a direct jar URL.",
                "warning"
            );
        } else if (provider === "curseforge" && !payload.curseforge_configured) {
            showMessage(
                "Add a free CurseForge API key below to search. URL paste works without a key.",
                "warning"
            );
        }
    }

    function curseForgeErrorMessage(raw) {
        const text = String(raw || "").trim();
        if (!text) {
            return "CurseForge request failed.";
        }
        const lower = text.toLowerCase();
        if (
            lower.includes("rejected the api key")
            || lower.includes("rate-limited")
            || lower.includes("403")
            || lower.includes("forbidden")
        ) {
            return (
                "CurseForge rejected the API key (invalid or rate-limited). "
                + "Regenerate at console.curseforge.com, wait if you hit limits, "
                + "then paste the new key and save again. Modrinth and URL paste still work."
            );
        }
        return text;
    }

    async function runSearch() {
        if (busy) {
            return;
        }
        const q = (searchInput.value || "").trim();
        if (!q) {
            showMessage("Enter a search term.", "warning");
            return;
        }
        if (provider === "curseforge" && !context.curseforge_configured) {
            showMessage(
                "Save a CurseForge API key first (console.curseforge.com → API keys).",
                "warning"
            );
            return;
        }
        busy = true;
        const label = provider === "curseforge" ? "CurseForge" : "Modrinth";
        showMessage(`Searching ${label}…`);
        try {
            const payload = await api(
                `${API_BASE}/search?q=${encodeURIComponent(q)}&limit=20&provider=${encodeURIComponent(provider)}`
            );
            applyContext(payload);
            renderResults(payload.results || []);
            showMessage(`Found ${payload.total || 0} results on ${label}.`, "success");
        } catch (error) {
            const msg = error.message || "Search failed.";
            showMessage(
                provider === "curseforge" ? curseForgeErrorMessage(msg) : msg,
                "error"
            );
        } finally {
            busy = false;
        }
    }

    async function installProject(projectId, projectProvider) {
        if (busy || !projectId) {
            return;
        }
        const source = projectProvider || provider;
        busy = true;
        showMessage(`Downloading from ${source === "curseforge" ? "CurseForge" : "Modrinth"}…`);
        try {
            const payload = await api(`${API_BASE}/install`, {
                method: "POST",
                body: JSON.stringify({
                    project_id: projectId,
                    provider: source,
                }),
            });
            applyContext(payload);
            const name = payload.installed && payload.installed.name;
            showMessage(
                name ? `Installed ${name}` : "Installed successfully.",
                "success"
            );
        } catch (error) {
            const msg = error.message || "Install failed.";
            showMessage(
                source === "curseforge" ? curseForgeErrorMessage(msg) : msg,
                "error"
            );
        } finally {
            busy = false;
        }
    }

    async function saveCurseForgeKey() {
        if (busy) {
            return;
        }
        const raw = (cfKeyInput && cfKeyInput.value) || "";
        busy = true;
        showMessage(raw.trim() ? "Verifying CurseForge API key…" : "Clearing CurseForge API key…");
        try {
            const payload = await api(`${API_BASE}/curseforge-key`, {
                method: "PUT",
                body: JSON.stringify({ api_key: raw }),
            });
            if (cfKeyInput) {
                cfKeyInput.value = "";
            }
            context.curseforge_configured = Boolean(payload.configured);
            showMessage(payload.message || "Saved.", "success");
            await loadContext();
        } catch (error) {
            showMessage(
                curseForgeErrorMessage(error.message || "Could not save API key."),
                "error"
            );
        } finally {
            busy = false;
        }
    }

    async function installUrl() {
        if (busy) {
            return;
        }
        const url = (urlInput.value || "").trim();
        if (!url) {
            showMessage("Paste a direct jar URL first.", "warning");
            return;
        }
        busy = true;
        showMessage("Downloading jar…");
        try {
            const payload = await api(`${API_BASE}/install-url`, {
                method: "POST",
                body: JSON.stringify({ url }),
            });
            applyContext(payload);
            urlInput.value = "";
            const name = payload.installed && payload.installed.name;
            showMessage(
                name ? `Installed ${name}` : "Installed successfully.",
                "success"
            );
        } catch (error) {
            showMessage(error.message || "URL install failed.", "error");
        } finally {
            busy = false;
        }
    }

    function injectPanel() {
        if (document.getElementById("mods")) {
            panel = document.getElementById("mods");
            return true;
        }
        const files = document.getElementById("files");
        const players = document.getElementById("players");
        const backups = document.getElementById("backups");
        const target = files || players || backups;
        if (!target || !target.parentNode) {
            return false;
        }

        panel = document.createElement("article");
        panel.id = "mods";
        panel.className = "panel section mods-panel";

        const header = document.createElement("div");
        header.className = "section-header";
        const copy = document.createElement("div");
        const title = document.createElement("h2");
        title.className = "section-title";
        title.textContent = "Mods & plugins";
        note = document.createElement("span");
        note.className = "section-note";
        note.textContent = "Loading…";
        copy.append(title, note);
        header.appendChild(copy);

        const searchBar = document.createElement("div");
        searchBar.className = "mods-toolbar";
        providerSelect = document.createElement("select");
        providerSelect.className = "mods-button";
        providerSelect.innerHTML = `
            <option value="modrinth">Modrinth</option>
            <option value="curseforge">CurseForge</option>
        `;
        providerSelect.value = provider;
        providerSelect.addEventListener("change", () => {
            provider = providerSelect.value || "modrinth";
            searchInput.placeholder = provider === "curseforge"
                ? "Search CurseForge…"
                : "Search Modrinth…";
            if (provider === "curseforge" && !context.curseforge_configured) {
                showMessage(
                    "Add a free CurseForge API key below to search.",
                    "warning"
                );
            }
        });
        searchInput = document.createElement("input");
        searchInput.type = "search";
        searchInput.placeholder = "Search Modrinth…";
        const searchBtn = document.createElement("button");
        searchBtn.type = "button";
        searchBtn.className = "mods-button primary";
        searchBtn.textContent = "Search";
        searchBtn.addEventListener("click", runSearch);
        searchInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                runSearch();
            }
        });
        searchBar.append(providerSelect, searchInput, searchBtn);

        const cfBar = document.createElement("div");
        cfBar.className = "mods-toolbar";
        cfKeyInput = document.createElement("input");
        cfKeyInput.type = "password";
        cfKeyInput.autocomplete = "off";
        cfKeyInput.placeholder = "Paste CurseForge API key (console.curseforge.com)";
        const cfBtn = document.createElement("button");
        cfBtn.type = "button";
        cfBtn.className = "mods-button";
        cfBtn.textContent = "Save CF key";
        cfBtn.addEventListener("click", saveCurseForgeKey);
        cfBar.append(cfKeyInput, cfBtn);

        const urlBar = document.createElement("div");
        urlBar.className = "mods-toolbar";
        urlInput = document.createElement("input");
        urlInput.type = "url";
        urlInput.placeholder = "Or paste a direct .jar URL (Modrinth/GitHub/ForgeCDN)";
        const urlBtn = document.createElement("button");
        urlBtn.type = "button";
        urlBtn.className = "mods-button";
        urlBtn.textContent = "Install URL";
        urlBtn.addEventListener("click", installUrl);
        urlBar.append(urlInput, urlBtn);

        const grid = document.createElement("div");
        grid.className = "mods-grid";
        const left = document.createElement("div");
        left.className = "mods-section";
        const leftTitle = document.createElement("h3");
        leftTitle.textContent = "Search results";
        resultsBox = document.createElement("div");
        left.append(leftTitle, resultsBox);

        const right = document.createElement("div");
        right.className = "mods-section";
        const rightTitle = document.createElement("h3");
        rightTitle.textContent = "Installed";
        installedBox = document.createElement("div");
        right.append(rightTitle, installedBox);
        grid.append(left, right);

        message = document.createElement("div");
        message.className = "mods-message";

        panel.append(header, searchBar, cfBar, urlBar, grid, message);
        target.parentNode.insertBefore(panel, target.nextSibling);
        return true;
    }

    async function boot() {
        injectStyles();
        injectNav();
        if (!injectPanel()) {
            window.setTimeout(boot, 250);
            return;
        }
        try {
            await loadContext();
        } catch (error) {
            showMessage(error.message || "Could not load mods panel.", "error");
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
