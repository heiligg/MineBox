"use strict";

(() => {
    const API_BASE = "/api/v1/files";

    let panel;
    let note;
    let message;
    let breadcrumb;
    let quickLinks;
    let listing;
    let dropZone;
    let uploadInput;
    let folderInput;
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
            .files-picker {
                position: relative;
                display: inline-flex;
                overflow: hidden;
                border-radius: 10px;
            }
            .files-picker input[type="file"] {
                position: absolute;
                inset: 0;
                width: 100%;
                height: 100%;
                opacity: 0;
                cursor: pointer;
                font-size: 64px;
            }
            .files-panel { position: relative; }
            .files-panel.files-drop-active {
                outline: 2px dashed rgba(47, 111, 237, 0.8);
                outline-offset: 6px;
            }
            .files-drop {
                margin-top: 14px;
                padding: 16px;
                border: 1px dashed rgba(255,255,255,0.18);
                border-radius: 12px;
                color: var(--muted);
                font-size: 13px;
                text-align: center;
            }
            .files-drop.active {
                border-color: rgba(47, 111, 237, 0.8);
                background: rgba(47, 111, 237, 0.12);
                color: var(--text);
            }
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

    function normalizeRelative(value) {
        return String(value || "").replace(/\\/g, "/").replace(/^\/+/, "");
    }

    function relativeFor(file) {
        if (!file) {
            return "";
        }
        const candidates = [
            file.webkitRelativePath,
            file.relativePath,
        ].map(normalizeRelative);
        const nested = candidates.find((value) => value.includes("/"))
            || candidates.find(Boolean)
            || "";
        if (nested && !nested.endsWith("/")) {
            return nested;
        }
        return file.name || "";
    }

    function attachRelative(file, relative) {
        try {
            Object.defineProperty(file, "relativePath", {
                value: relative,
                configurable: true,
            });
        } catch {
            file.relativePath = relative;
        }
        return file;
    }

    function filesFromList(fileList) {
        const out = [];
        if (!fileList) {
            return out;
        }
        for (let i = 0; i < fileList.length; i += 1) {
            const file = fileList[i];
            const relative = relativeFor(file);
            if (!file || !relative || relative.endsWith("/")) {
                continue;
            }
            out.push({
                kind: "file",
                file: attachRelative(file, relative),
                relative,
            });
        }
        return out;
    }

    function parentDirs(relative) {
        const parts = normalizeRelative(relative).split("/").filter(Boolean);
        parts.pop();
        const dirs = [];
        let built = "";
        for (const part of parts) {
            built = built ? `${built}/${part}` : part;
            dirs.push(built);
        }
        return dirs;
    }

    function collectDirs(items) {
        const dirs = new Set();
        for (const item of items) {
            if (item.kind === "dir" && item.relative) {
                dirs.add(item.relative);
            }
            if (item.kind === "file" && item.relative) {
                parentDirs(item.relative).forEach((dir) => dirs.add(dir));
            }
        }
        return [...dirs].sort(
            (a, b) => a.split("/").length - b.split("/").length || a.localeCompare(b)
        );
    }

    function isFileDrag(event) {
        const types = event.dataTransfer && event.dataTransfer.types;
        if (!types) {
            return false;
        }
        return [...types].includes("Files");
    }

    function captureDrop(event) {
        const entries = [];
        const items = event.dataTransfer && event.dataTransfer.items;
        // Call webkitGetAsEntry before touching .files. Chrome drops directory
        // entries if getAsFileSystemHandle() or .files is read first, especially
        // on http:// LAN pages.
        if (items) {
            for (let i = 0; i < items.length; i += 1) {
                const item = items[i];
                if (typeof item.webkitGetAsEntry === "function") {
                    const entry = item.webkitGetAsEntry();
                    if (entry) {
                        entries.push(entry);
                    }
                }
            }
        }
        return { entries };
    }

    function readAllEntries(dirEntry) {
        const reader = dirEntry.createReader();
        return new Promise((resolve, reject) => {
            const all = [];
            const pump = () => {
                reader.readEntries((batch) => {
                    if (!batch.length) {
                        resolve(all);
                        return;
                    }
                    all.push(...batch);
                    pump();
                }, reject);
            };
            pump();
        });
    }

    async function walkEntry(entry, prefix) {
        const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
        if (entry.isFile) {
            const file = await new Promise((resolve, reject) => {
                entry.file(resolve, reject);
            });
            return [{ kind: "file", file: attachRelative(file, relative), relative }];
        }
        if (!entry.isDirectory) {
            return [];
        }
        const children = await readAllEntries(entry);
        const items = [{ kind: "dir", relative }];
        for (const child of children) {
            items.push(...await walkEntry(child, relative));
        }
        return items;
    }

    async function itemsFromDrop(captured) {
        const walked = [];
        for (const entry of captured.entries || []) {
            walked.push(...await walkEntry(entry, ""));
        }
        return walked;
    }

    function encodeRel(relative) {
        const bytes = new TextEncoder().encode(relative);
        let binary = "";
        bytes.forEach((byte) => {
            binary += String.fromCharCode(byte);
        });
        return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
    }

    const CRC_TABLE = (() => {
        const table = new Uint32Array(256);
        for (let index = 0; index < 256; index += 1) {
            let value = index;
            for (let bit = 0; bit < 8; bit += 1) {
                value = value & 1 ? 0xEDB88320 ^ (value >>> 1) : value >>> 1;
            }
            table[index] = value >>> 0;
        }
        return table;
    })();

    function crc32(bytes) {
        let value = 0xFFFFFFFF;
        for (let index = 0; index < bytes.length; index += 1) {
            value = CRC_TABLE[(value ^ bytes[index]) & 0xFF] ^ (value >>> 8);
        }
        return (value ^ 0xFFFFFFFF) >>> 0;
    }

    function u16(value) {
        return new Uint8Array([value & 0xFF, (value >>> 8) & 0xFF]);
    }

    function u32(value) {
        return new Uint8Array([
            value & 0xFF,
            (value >>> 8) & 0xFF,
            (value >>> 16) & 0xFF,
            (value >>> 24) & 0xFF,
        ]);
    }

    function isZipName(name) {
        const lower = String(name || "").toLowerCase();
        return lower.endsWith(".zip") || lower.endsWith(".mcworld") || lower.endsWith(".tar.gz");
    }

    function looksLikeWorld(items) {
        return (items || []).some((item) => {
            const relative = String(item.relative || (item.file && item.file.name) || "")
                .replace(/\\/g, "/");
            return relative === "level.dat" || relative.endsWith("/level.dat");
        });
    }

    async function zipWorldItems(items) {
        const encoder = new TextEncoder();
        const locals = [];
        const centrals = [];
        let offset = 0;
        const files = items.filter((item) => item.kind === "file" && item.file);
        let count = 0;
        for (let index = 0; index < files.length; index += 1) {
            const item = files[index];
            const relative = String(item.relative || item.file.name || "")
                .replace(/\\/g, "/")
                .replace(/^\/+/, "");
            if (!relative || relative.endsWith("session.lock")) {
                continue;
            }
            showMessage(`Packing world ${index + 1}/${files.length}: ${relative}`);
            const bytes = new Uint8Array(await item.file.arrayBuffer());
            const nameBytes = encoder.encode(relative);
            const crc = crc32(bytes);
            const local = [
                u32(0x04034b50),
                u16(20),
                u16(0),
                u16(0),
                u16(0),
                u16(0),
                u32(crc),
                u32(bytes.length),
                u32(bytes.length),
                u16(nameBytes.length),
                u16(0),
                nameBytes,
                bytes,
            ];
            locals.push(...local);
            centrals.push(
                u32(0x02014b50),
                u16(20),
                u16(20),
                u16(0),
                u16(0),
                u16(0),
                u16(0),
                u32(crc),
                u32(bytes.length),
                u32(bytes.length),
                u16(nameBytes.length),
                u16(0),
                u16(0),
                u16(0),
                u16(0),
                u32(0),
                u32(offset),
                nameBytes
            );
            offset += 30 + nameBytes.length + bytes.length;
            count += 1;
        }
        if (!count) {
            throw new Error("That folder did not contain a Minecraft world.");
        }
        const centralSize = centrals.reduce((sum, part) => sum + part.length, 0);
        const end = [
            u32(0x06054b50),
            u16(0),
            u16(0),
            u16(count),
            u16(count),
            u32(centralSize),
            u32(offset),
            u16(0),
        ];
        return new Blob([...locals, ...centrals, ...end], { type: "application/zip" });
    }

    async function uploadWorldFile(file, filename) {
        if (busy) {
            showMessage("Wait for the current file operation to finish.", "warning");
            return;
        }
        if (!window.confirm(
            "Replace the multiplayer world with this singleplayer save? "
            + "The current world will be renamed as a backup, and the server will be stopped."
        )) {
            return;
        }
        busy = true;
        try {
            showMessage("Uploading world save… this can take a minute.");
            const form = new FormData();
            form.append("file", file, filename || file.name || "world.zip");
            const response = await fetch(`${API_BASE}/upload-world`, {
                method: "POST",
                credentials: "same-origin",
                body: form,
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(detailFromPayload(payload));
            }
            showMessage(payload.message || "World save installed.", "success");
            if (payload.entries) {
                renderListing(payload);
            } else {
                await loadPath("");
                showMessage(payload.message || "World save installed.", "success");
            }
        } catch (error) {
            showMessage(error.message || "Could not install that world save.", "error");
        } finally {
            busy = false;
        }
    }

    async function uploadWorldFromItems(items) {
        const blob = await zipWorldItems(items);
        await uploadWorldFile(blob, "world-save.zip");
    }

    async function ensureFolder(relative) {
        const path = currentPath ? joinPath(currentPath, relative) : relative;
        await api(`${API_BASE}/mkdir`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path }),
        }).catch((error) => {
            const text = String(error && error.message || "");
            if (!/already exists/i.test(text)) {
                throw error;
            }
        });
    }

    async function uploadOne(file, relative) {
        const form = new FormData();
        form.append("path", currentPath || "");
        form.append("relative_path", relative);
        form.append("rel", encodeRel(relative));
        form.append("file", file, file.name);
        const params = new URLSearchParams({ refresh: "false" });
        if (relative.length < 800) {
            params.set("nested", relative);
        }
        const response = await fetch(`${API_BASE}/upload?${params}`, {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-MineBox-Relative-Path": relative },
            body: form,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(detailFromPayload(payload) || `Failed: ${relative}`);
        }
        return payload;
    }

    async function uploadItems(items) {
        const dirs = collectDirs(items);
        const files = items.filter((item) => item.kind === "file" && item.file);
        if (!dirs.length && !files.length) {
            showMessage("Nothing to upload from that folder.", "warning");
            return;
        }
        if (busy) {
            showMessage("Wait for the current file operation to finish.", "warning");
            return;
        }
        busy = true;
        let uploaded = 0;
        const failures = [];
        try {
            for (const relative of dirs) {
                try {
                    await ensureFolder(relative);
                } catch (error) {
                    failures.push(`${relative}/ (${error.message || "mkdir failed"})`);
                }
            }
            const queue = [...files];
            const workers = Math.min(4, queue.length || 1);
            const runWorker = async () => {
                while (queue.length) {
                    const item = queue.shift();
                    const relative = item.relative || relativeFor(item.file);
                    showMessage(
                        `Uploading ${uploaded + failures.length + 1}/${files.length}: ${relative}`
                    );
                    try {
                        await uploadOne(item.file, relative);
                        uploaded += 1;
                    } catch (error) {
                        failures.push(`${relative} (${error.message || "failed"})`);
                    }
                }
            };
            await Promise.all(Array.from({ length: workers }, runWorker));
            if (!failures.length) {
                showMessage(
                    files.length === 0
                        ? `Created ${dirs.length} folder${dirs.length === 1 ? "" : "s"}`
                        : uploaded === 1
                            ? `Uploaded ${files[0].relative || relativeFor(files[0].file)}`
                            : `Uploaded ${uploaded} files`,
                    "success"
                );
            } else {
                showMessage(
                    `Uploaded ${uploaded}/${files.length}. Failed: ${failures.slice(0, 4).join("; ")}${
                        failures.length > 4 ? ` (+${failures.length - 4} more)` : ""
                    }`,
                    uploaded ? "warning" : "error"
                );
            }
        } finally {
            if (uploadInput) {
                uploadInput.value = "";
            }
            if (folderInput) {
                folderInput.value = "";
            }
            busy = false;
        }
        const summary = message ? message.textContent : "";
        const summaryType = message
            ? [...message.classList].find((name) =>
                ["success", "warning", "error"].includes(name)
            ) || ""
            : "";
        await loadPath(currentPath);
        if (summary) {
            showMessage(summary, summaryType);
        }
    }

    async function uploadFiles(fileList) {
        await uploadItems(filesFromList(fileList));
    }

    async function uploadSelected() {
        await uploadFiles(uploadInput.files);
    }

    async function uploadFolderSelected() {
        const items = filesFromList(folderInput.files);
        if (looksLikeWorld(items)) {
            await uploadWorldFromItems(items);
            return;
        }
        if (items.length > 1 && !items.some((item) => item.relative.includes("/"))) {
            showMessage(
                "Folder names were missing from that picker. For a Minecraft world, zip the save folder and use Upload world save.",
                "warning"
            );
        }
        await uploadItems(items);
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

        const filesPicker = makePicker({
            label: "Upload files",
            primary: true,
            multiple: true,
            directory: false,
            onChange: uploadSelected,
        });
        uploadInput = filesPicker.input;

        const folderPicker = makePicker({
            label: "Upload folder",
            primary: false,
            multiple: true,
            directory: true,
            onChange: uploadFolderSelected,
        });
        folderInput = folderPicker.input;

        const worldPicker = makePicker({
            label: "Upload world save",
            primary: false,
            multiple: false,
            directory: false,
            accept: ".zip,.mcworld,.tar.gz,application/zip",
            onChange: async () => {
                const file = worldPicker.input.files && worldPicker.input.files[0];
                worldPicker.input.value = "";
                if (file) {
                    await uploadWorldFile(file, file.name);
                }
            },
        });

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

        toolbar.append(
            filesPicker.wrap,
            folderPicker.wrap,
            worldPicker.wrap,
            mkdirInput,
            mkdirBtn,
            refreshBtn
        );

        listing = document.createElement("div");
        dropZone = document.createElement("div");
        dropZone.className = "files-drop";
        dropZone.textContent = "To load a singleplayer world: zip the save folder (the one with level.dat) and use Upload world save, or drop that .zip here.";
        message = document.createElement("div");
        message.className = "files-message";

        panel.append(header, quickLinks, breadcrumb, toolbar, dropZone, listing, message);
        bindDropTarget();
        target.parentNode.insertBefore(panel, target);
        return true;
    }

    function makePicker({ label, primary, multiple, directory, accept, onChange }) {
        const wrap = document.createElement("div");
        wrap.className = "files-picker";
        const button = document.createElement("button");
        button.type = "button";
        button.className = primary ? "files-button primary" : "files-button";
        button.textContent = label;
        button.tabIndex = -1;
        const input = document.createElement("input");
        input.type = "file";
        if (multiple) {
            input.multiple = true;
        }
        if (accept) {
            input.accept = accept;
        }
        if (directory) {
            input.setAttribute("webkitdirectory", "");
            input.setAttribute("directory", "");
            try {
                input.webkitdirectory = true;
                input.directory = true;
            } catch {
                // Attribute-only browsers still open a folder picker.
            }
            input.multiple = true;
        }
        input.addEventListener("change", onChange);
        wrap.append(button, input);
        return { wrap, input };
    }

    function overFilesPanel(event) {
        return Boolean(panel && (event.target === panel || panel.contains(event.target)));
    }

    function bindDropTarget() {
        const setActive = (on) => {
            if (panel) {
                panel.classList.toggle("files-drop-active", on);
            }
            if (dropZone) {
                dropZone.classList.toggle("active", on);
            }
        };
        const onDragOver = (event) => {
            if (!isFileDrag(event) || !overFilesPanel(event)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            event.dataTransfer.dropEffect = "copy";
            setActive(true);
        };
        const onDragLeave = (event) => {
            if (!panel || panel.contains(event.relatedTarget)) {
                return;
            }
            setActive(false);
        };
        const onDrop = (event) => {
            if (!isFileDrag(event) || !overFilesPanel(event)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            setActive(false);
            const captured = captureDrop(event);
            itemsFromDrop(captured)
                .then((items) => {
                    if (!items.length) {
                        showMessage(
                            "Could not read that drop. Zip the world save folder and use Upload world save.",
                            "warning"
                        );
                        return;
                    }
                    const zipItem = items.find((item) =>
                        item.kind === "file" && item.file && isZipName(item.file.name)
                    );
                    if (items.length === 1 && zipItem) {
                        return uploadWorldFile(zipItem.file, zipItem.file.name);
                    }
                    if (looksLikeWorld(items)) {
                        return uploadWorldFromItems(items);
                    }
                    return uploadItems(items);
                })
                .catch((error) => {
                    showMessage(error.message || "Could not read that folder.", "error");
                });
        };
        document.addEventListener("dragover", onDragOver, true);
        document.addEventListener("drop", onDrop, true);
        document.addEventListener("dragleave", onDragLeave, true);
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
