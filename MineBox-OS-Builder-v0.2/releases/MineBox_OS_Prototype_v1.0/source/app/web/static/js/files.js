"use strict";

(() => {
    const API_BASE = "/api/v1/files";

    let panel;
    let note;
    let message;
    let breadcrumb;
    let quickLinks;
    let listing;
    let uploadInput;
    let mkdirInput;
    let busy = false;
    let currentPath = "";

    function injectStyles() {
        if (document.getElementById("minebox-files-styles")) {
            return;
        }

        const style = document.createElement("style");
        style.id = "minebox-files-styles";
        style.textContent = `
            .files-panel { scroll-margin-top: 24px; }
            .files-toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                align-items: center;
                margin-top: 16px;
            }
            .files-toolbar input[type="text"] {
                flex: 1 1 160px;
                min-width: 140px;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                font: inherit;
                padding: 10px 12px;
            }
            .files-button {
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                background: rgba(255,255,255,0.04);
                color: var(--text);
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 10px 14px;
            }
            .files-button.primary {
                background: #2f6fed;
                border-color: #2f6fed;
            }
            .files-button.danger {
                color: #ff9c9c;
            }
            .files-button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .files-quick {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 14px;
            }
            .files-chip {
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 999px;
                background: rgba(255,255,255,0.03);
                color: var(--muted);
                cursor: pointer;
                font: inherit;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 12px;
            }
            .files-chip.active {
                color: var(--text);
                border-color: rgba(47, 111, 237, 0.7);
                background: rgba(47, 111, 237, 0.18);
            }
            .files-breadcrumb {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                align-items: center;
                margin-top: 16px;
                color: var(--muted);
                font-size: 13px;
            }
            .files-breadcrumb button {
                border: 0;
                background: transparent;
                color: #9ec1ff;
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 0;
            }
            .files-breadcrumb .sep { opacity: 0.45; }
            .files-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 14px;
            }
            .files-table th,
            .files-table td {
                padding: 10px 8px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
                text-align: left;
                vertical-align: middle;
            }
            .files-table th {
                color: var(--muted);
                font-size: 11px;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .files-name-btn {
                border: 0;
                background: transparent;
                color: var(--text);
                cursor: pointer;
                font: inherit;
                font-weight: 700;
                padding: 0;
                text-align: left;
            }
            .files-name-btn.dir { color: #9ec1ff; }
            .files-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                justify-content: flex-end;
            }
            .files-empty {
                margin-top: 18px;
                color: var(--muted);
                font-size: 14px;
            }
            .files-message {
                display: none;
                margin-top: 14px;
                padding: 12px 14px;
                border-radius: 10px;
                font-size: 14px;
            }
            .files-message.visible { display: block; }
            .files-message.success {
                background: rgba(80, 180, 100, 0.15);
                color: #8ee895;
            }
            .files-message.error {
                background: rgba(220, 80, 80, 0.12);
                color: #ff9c9c;
            }
            .files-message.warning {
                background: rgba(255, 180, 60, 0.12);
                color: #ffd27a;
            }
            .files-hidden-input { display: none; }
        `;
        document.head.appendChild(style);
    }

    function injectNav() {
        const nav = document.querySelector(".sidebar-nav, nav, .nav");
        if (!nav || document.getElementById("files-nav-item")) {
            return;
        }

        const link = document.createElement("a");
        link.id = "files-nav-item";
        link.className = "nav-item";
        link.href = "#files";
        link.innerHTML = `
            <span class="nav-icon" aria-hidden="true">▣</span>
            <span class="nav-text">Files</span>
        `;

        const backupsLink = [...nav.querySelectorAll(".nav-item")].find(
            (item) => item.getAttribute("href") === "#backups"
                || item.textContent.trim().includes("Backup")
        );
        const consoleLink = [...nav.querySelectorAll(".nav-item")].find(
            (item) => item.getAttribute("href") === "#console"
                || item.textContent.trim().includes("Console")
        );
        const anchor = backupsLink || consoleLink;
        if (anchor) {
            nav.insertBefore(link, anchor);
        } else {
            nav.appendChild(link);
        }
    }

    function showMessage(text, type = "") {
        if (!message) {
            return;
        }
        message.textContent = text || "";
        message.className = `files-message${text ? ` visible ${type}` : ""}`.trim();
    }

    function formatSize(bytes) {
        const value = Number(bytes) || 0;
        if (value < 1024) {
            return `${value} B`;
        }
        if (value < 1024 * 1024) {
            return `${(value / 1024).toFixed(1)} KB`;
        }
        if (value < 1024 * 1024 * 1024) {
            return `${(value / (1024 * 1024)).toFixed(1)} MB`;
        }
        return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    }

    function detailFromPayload(payload) {
        if (!payload) {
            return "Request failed.";
        }
        if (typeof payload.detail === "string") {
            return payload.detail;
        }
        if (payload.detail && typeof payload.detail.message === "string") {
            return payload.detail.message;
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
                ...(options.headers || {}),
            },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(detailFromPayload(payload));
        }
        return payload;
    }

    function joinPath(base, name) {
        if (!base) {
            return name;
        }
        return `${base.replace(/\/+$/, "")}/${name}`;
    }

    function renderBreadcrumb(path, serverName) {
        breadcrumb.innerHTML = "";
        const rootBtn = document.createElement("button");
        rootBtn.type = "button";
        rootBtn.textContent = serverName || "Server";
        rootBtn.addEventListener("click", () => loadPath(""));
        breadcrumb.appendChild(rootBtn);

        const parts = path ? path.split("/").filter(Boolean) : [];
        let built = "";
        for (const part of parts) {
            const sep = document.createElement("span");
            sep.className = "sep";
            sep.textContent = "/";
            breadcrumb.appendChild(sep);
            built = joinPath(built, part);
            const btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = part;
            const target = built;
            btn.addEventListener("click", () => loadPath(target));
            breadcrumb.appendChild(btn);
        }
    }

    function renderQuick(activePath, dirs) {
        quickLinks.innerHTML = "";
        for (const dir of dirs || ["mods", "plugins", "config", "world"]) {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = `files-chip${activePath === dir ? " active" : ""}`;
            chip.textContent = dir;
            chip.addEventListener("click", () => loadPath(dir));
            quickLinks.appendChild(chip);
        }
    }

    function renderListing(payload) {
        currentPath = payload.path || "";
        note.textContent = payload.server_running
            ? "Server is running — world edits are locked"
            : "Active server files";
        renderBreadcrumb(currentPath, payload.server_name);
        renderQuick(currentPath, payload.quick_dirs);

        listing.innerHTML = "";
        const entries = payload.entries || [];
        if (!entries.length) {
            const empty = document.createElement("p");
            empty.className = "files-empty";
            empty.textContent = "This folder is empty.";
            listing.appendChild(empty);
            return;
        }

        const table = document.createElement("table");
        table.className = "files-table";
        table.innerHTML = `
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Size</th>
                    <th></th>
                </tr>
            </thead>
        `;
        const tbody = document.createElement("tbody");

        if (currentPath) {
            const upRow = document.createElement("tr");
            const upName = document.createElement("td");
            const upBtn = document.createElement("button");
            upBtn.type = "button";
            upBtn.className = "files-name-btn dir";
            upBtn.textContent = "↑ Parent folder";
            const parent = currentPath.includes("/")
                ? currentPath.split("/").slice(0, -1).join("/")
                : "";
            upBtn.addEventListener("click", () => loadPath(parent));
            upName.appendChild(upBtn);
            upRow.append(upName, document.createElement("td"), document.createElement("td"));
            tbody.appendChild(upRow);
        }

        for (const entry of entries) {
            const row = document.createElement("tr");
            const nameCell = document.createElement("td");
            const sizeCell = document.createElement("td");
            const actionCell = document.createElement("td");
            actionCell.className = "files-actions";

            if (entry.type === "dir") {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "files-name-btn dir";
                btn.textContent = `${entry.name}/`;
                btn.addEventListener("click", () => loadPath(entry.path));
                nameCell.appendChild(btn);
                sizeCell.textContent = "—";
            } else {
                const label = document.createElement("span");
                label.className = "files-name-btn";
                label.textContent = entry.name;
                nameCell.appendChild(label);
                sizeCell.textContent = formatSize(entry.size);

                const download = document.createElement("a");
                download.className = "files-button";
                download.textContent = "Download";
                download.href = `${API_BASE}/download?path=${encodeURIComponent(entry.path)}`;
                actionCell.appendChild(download);
            }

            const del = document.createElement("button");
            del.type = "button";
            del.className = "files-button danger";
            del.textContent = "Delete";
            del.addEventListener("click", () => deleteEntry(entry));
            actionCell.appendChild(del);

            row.append(nameCell, sizeCell, actionCell);
            tbody.appendChild(row);
        }

        table.appendChild(tbody);
        listing.appendChild(table);
    }

    async function loadPath(path) {
        if (busy) {
            return;
        }
        busy = true;
        showMessage("");
        note.textContent = "Loading…";
        try {
            const payload = await api(
                `${API_BASE}?path=${encodeURIComponent(path || "")}`
            );
            renderListing(payload);
        } catch (error) {
            showMessage(error.message || "Could not load files.", "error");
            note.textContent = "Unable to load folder";
        } finally {
            busy = false;
        }
    }

    async function createFolder() {
        const name = (mkdirInput.value || "").trim().replace(/[\\/]/g, "");
        if (!name) {
            showMessage("Enter a folder name.", "warning");
            return;
        }
        const path = joinPath(currentPath, name);
        busy = true;
        try {
            const payload = await api(`${API_BASE}/mkdir`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path }),
            });
            mkdirInput.value = "";
            showMessage(`Created ${name}/`, "success");
            renderListing(payload);
        } catch (error) {
            showMessage(error.message || "Could not create folder.", "error");
        } finally {
            busy = false;
        }
    }

    async function uploadSelected() {
        const file = uploadInput.files && uploadInput.files[0];
        if (!file) {
            return;
        }
        const form = new FormData();
        form.append("path", currentPath || "");
        form.append("file", file, file.name);
        busy = true;
        showMessage(`Uploading ${file.name}…`);
        try {
            const response = await fetch(`${API_BASE}/upload`, {
                method: "POST",
                credentials: "same-origin",
                body: form,
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(detailFromPayload(payload));
            }
            showMessage(`Uploaded ${file.name}`, "success");
            renderListing(payload);
        } catch (error) {
            showMessage(error.message || "Upload failed.", "error");
        } finally {
            uploadInput.value = "";
            busy = false;
        }
    }

    async function deleteEntry(entry) {
        const label = entry.type === "dir" ? `${entry.name}/` : entry.name;
        if (!window.confirm(`Delete ${label}? This cannot be undone.`)) {
            return;
        }
        busy = true;
        try {
            const payload = await api(
                `${API_BASE}?path=${encodeURIComponent(entry.path)}`,
                { method: "DELETE" }
            );
            showMessage(`Deleted ${label}`, "success");
            renderListing(payload);
        } catch (error) {
            showMessage(error.message || "Delete failed.", "error");
        } finally {
            busy = false;
        }
    }

    function injectPanel() {
        if (document.getElementById("files")) {
            panel = document.getElementById("files");
            return true;
        }

        const backups = document.getElementById("backups");
        const settings = document.getElementById("settings");
        const target = backups || settings;
        if (!target || !target.parentNode) {
            return false;
        }

        panel = document.createElement("article");
        panel.id = "files";
        panel.className = "panel section files-panel";

        const header = document.createElement("div");
        header.className = "section-header";
        const copy = document.createElement("div");
        const title = document.createElement("h2");
        title.className = "section-title";
        title.textContent = "Files";
        note = document.createElement("span");
        note.className = "section-note";
        note.textContent = "Active server folder";
        copy.append(title, note);
        header.appendChild(copy);

        quickLinks = document.createElement("div");
        quickLinks.className = "files-quick";

        breadcrumb = document.createElement("div");
        breadcrumb.className = "files-breadcrumb";

        const toolbar = document.createElement("div");
        toolbar.className = "files-toolbar";

        const uploadBtn = document.createElement("button");
        uploadBtn.type = "button";
        uploadBtn.className = "files-button primary";
        uploadBtn.textContent = "Upload file";
        uploadInput = document.createElement("input");
        uploadInput.type = "file";
        uploadInput.className = "files-hidden-input";
        uploadBtn.addEventListener("click", () => uploadInput.click());
        uploadInput.addEventListener("change", uploadSelected);

        mkdirInput = document.createElement("input");
        mkdirInput.type = "text";
        mkdirInput.placeholder = "New folder name";
        mkdirInput.maxLength = 120;

        const mkdirBtn = document.createElement("button");
        mkdirBtn.type = "button";
        mkdirBtn.className = "files-button";
        mkdirBtn.textContent = "New folder";
        mkdirBtn.addEventListener("click", createFolder);

        const refreshBtn = document.createElement("button");
        refreshBtn.type = "button";
        refreshBtn.className = "files-button";
        refreshBtn.textContent = "Refresh";
        refreshBtn.addEventListener("click", () => loadPath(currentPath));

        toolbar.append(uploadBtn, uploadInput, mkdirInput, mkdirBtn, refreshBtn);

        listing = document.createElement("div");
        message = document.createElement("div");
        message.className = "files-message";

        panel.append(header, quickLinks, breadcrumb, toolbar, listing, message);
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
        loadPath("");
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
