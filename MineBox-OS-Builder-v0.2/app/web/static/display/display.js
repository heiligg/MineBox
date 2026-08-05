/* MineBox local display UI — 800×480 focus navigation (no pointer required). */
(function () {
  const IDLE_MS = 120000;
  const POLL_MS = 2000;
  const EVENT_MS = 120;
  const RETRY_MAX_MS = 8000;

  const state = {
    screen: "home",
    focus: 0,
    wrap: true,
    snapshot: null,
    stale: false,
    backendOk: true,
    lastOkAt: 0,
    message: "",
    progress: "",
    confirmAction: null,
    confirmLabel: "",
    diagnosticsMode: false,
    actionMap: null,
    idleTimer: null,
    retryDelay: 1000,
    liveInputs: { left: false, right: false, enc: false, deltaHint: "" },
  };

  const SCREENS = {
    home: {
      title: "Home",
      items: () => [
        { id: "nav_server", label: "Server" },
        { id: "nav_backups", label: "Backups" },
        { id: "nav_network", label: "Network" },
        { id: "nav_system", label: "System" },
        { id: "nav_power", label: "Power" },
        { id: "nav_diagnostics", label: "Hardware diagnostics" },
      ],
    },
    server: {
      title: "Server",
      items: () => serverActions(),
    },
    server_details: {
      title: "Server details",
      items: () => [{ id: "nav_back", label: "Back" }],
    },
    backups: {
      title: "Backups",
      items: () => [
        { id: "backup_create", label: "Create backup" },
        { id: "nav_back", label: "Back" },
      ],
    },
    network: {
      title: "Network",
      items: () => [{ id: "nav_back", label: "Back" }],
    },
    system: {
      title: "System",
      items: () => [
        { id: "nav_diagnostics", label: "Hardware diagnostics" },
        { id: "nav_back", label: "Back" },
      ],
    },
    power: {
      title: "Power",
      items: () => [
        { id: "services_restart", label: "Restart MineBox services" },
        { id: "device_reboot", label: "Reboot device" },
        { id: "device_shutdown", label: "Shut down device" },
        { id: "nav_back", label: "Back" },
      ],
    },
    confirm: {
      title: "Confirm",
      items: () => [
        { id: "confirm_yes", label: "Confirm" },
        { id: "confirm_no", label: "Cancel" },
      ],
    },
    setup: {
      title: "Setup required",
      items: () => [{ id: "nav_diagnostics", label: "Hardware diagnostics" }],
    },
    degraded: {
      title: "Backend unavailable",
      items: () => [{ id: "retry", label: "Retry connection" }],
    },
    diagnostics: {
      title: "Hardware diagnostics",
      items: () => [{ id: "nav_back", label: "Exit diagnostics" }],
    },
  };

  function foundation() {
    return (state.snapshot && state.snapshot.foundation) || {};
  }

  function mc() {
    const f = foundation();
    return f.minecraft || f.minecraft_state || {};
  }

  function system() {
    const f = foundation();
    return f.system || f.system_health || {};
  }

  function serverActions() {
    const st = String(mc().value || mc().state || mc().status || "").toUpperCase();
    const items = [];
    if (!st.includes("RUNNING")) {
      items.push({ id: "server_start", label: "Start" });
    }
    if (st.includes("RUNNING") || st.includes("STARTING")) {
      items.push({ id: "server_stop", label: "Stop" });
      items.push({ id: "server_restart", label: "Restart" });
    }
    items.push({ id: "backup_create", label: "Backup" });
    items.push({ id: "nav_server_details", label: "Details" });
    items.push({ id: "nav_back", label: "Back" });
    return items;
  }

  function currentItems() {
    const def = SCREENS[state.screen] || SCREENS.home;
    return def.items();
  }

  function resetIdle() {
    if (state.idleTimer) clearTimeout(state.idleTimer);
    if (["home", "setup", "degraded", "confirm"].includes(state.screen)) return;
    state.idleTimer = setTimeout(() => {
      go("home");
      render();
    }, IDLE_MS);
  }

  function go(screen) {
    state.screen = screen;
    state.focus = 0;
    state.message = "";
    if (screen !== "confirm") {
      state.confirmAction = null;
      state.confirmLabel = "";
    }
    state.diagnosticsMode = screen === "diagnostics";
    resetIdle();
  }

  function clampFocus() {
    const n = currentItems().length;
    if (n <= 0) {
      state.focus = 0;
      return;
    }
    if (state.focus < 0) state.focus = state.wrap ? n - 1 : 0;
    if (state.focus >= n) state.focus = state.wrap ? 0 : n - 1;
  }

  function intentNext() {
    state.focus += 1;
    clampFocus();
  }
  function intentPrev() {
    state.focus -= 1;
    clampFocus();
  }
  function intentBack() {
    if (state.screen === "confirm") {
      go(state._confirmReturn || "home");
      return;
    }
    if (state.screen === "diagnostics") {
      go("system");
      return;
    }
    if (state.screen !== "home" && state.screen !== "setup" && state.screen !== "degraded") {
      go("home");
    }
  }

  function intentHome() {
    go("home");
  }

  function intentContext() {
    // No UI redesign — System is the appliance context/settings surface.
    go("system");
  }

  function intentPower() {
    go("power");
  }

  async function intentSelect() {
    const items = currentItems();
    const item = items[state.focus];
    if (!item) return;
    await activate(item.id, item.label);
  }

  function askConfirm(action, label) {
    state._confirmReturn = state.screen;
    state.confirmAction = action;
    state.confirmLabel = label;
    go("confirm");
  }

  async function activate(id, label) {
    if (state.diagnosticsMode && id !== "nav_back") {
      state.message = "Diagnostics mode — actions disabled.";
      return;
    }
    if (id === "nav_back") return intentBack();
    if (id === "nav_server") return go("server");
    if (id === "nav_server_details") return go("server_details");
    if (id === "nav_backups") return go("backups");
    if (id === "nav_network") return go("network");
    if (id === "nav_system") return go("system");
    if (id === "nav_power") return go("power");
    if (id === "nav_diagnostics") return go("diagnostics");
    if (id === "retry") return refresh(true);
    if (id === "confirm_no") return intentBack();
    if (id === "confirm_yes") {
      if (state.confirmAction) {
        await runAction(state.confirmAction, true);
        go(state._confirmReturn || "home");
      }
      return;
    }
    if (id === "server_stop" || id === "server_restart" || id === "device_reboot" || id === "device_shutdown") {
      askConfirm(id, label);
      return;
    }
    await runAction(id, false);
  }

  async function runAction(action, confirm) {
    state.progress = "Working…";
    render();
    try {
      const res = await fetch("/api/v1/display/action", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ action, confirm: !!confirm }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Action failed");
      state.message = (data.result && data.result.message) || "Done.";
      state.progress = "";
      await refresh(true);
    } catch (err) {
      state.progress = "";
      state.message = err.message || "Action failed";
    }
  }

  function applyEvent(type) {
    if (state.diagnosticsMode) {
      state.liveInputs.deltaHint = type;
      if (type.includes("LEFT_BUTTON")) state.liveInputs.left = true;
      if (type.includes("RIGHT_BUTTON")) state.liveInputs.right = true;
      if (type.includes("ENCODER_PRESS") || type.includes("ENCODER_LONG")) state.liveInputs.enc = true;
      render();
      return;
    }
    const map = state.actionMap || {};
    const table = {
      ENCODER_CW: map.encoder_cw || map.encoder_right || "next",
      ENCODER_CCW: map.encoder_ccw || map.encoder_left || "prev",
      ENCODER_RIGHT: map.encoder_cw || map.encoder_right || "next",
      ENCODER_LEFT: map.encoder_ccw || map.encoder_left || "prev",
      ENCODER_PRESS: map.encoder_press || "select",
      ENCODER_LONG_PRESS: map.encoder_long_press || "back",
      LEFT_BUTTON_PRESS: map.left_button_press || "back",
      LEFT_BUTTON_HOLD: map.left_button_hold || "home",
      RIGHT_BUTTON_PRESS: map.right_button_press || "context",
      RIGHT_BUTTON_HOLD: map.right_button_hold || "power",
    };
    const intent = table[type];
    if (!intent) return;
    resetIdle();
    if (intent === "next") intentNext();
    else if (intent === "prev") intentPrev();
    else if (intent === "back") intentBack();
    else if (intent === "home") intentHome();
    else if (intent === "context") intentContext();
    else if (intent === "power") intentPower();
    else if (intent === "select") intentSelect();
    render();
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function renderStats(pairs) {
    const grid = el("div", "status-grid");
    for (const [label, value, tone] of pairs) {
      const box = el("div", "stat");
      box.appendChild(el("div", "label", label));
      const v = el("div", "value" + (tone ? " " + tone : ""), value);
      box.appendChild(v);
      grid.appendChild(box);
    }
    return grid;
  }

  function toneForState(text) {
    const u = String(text || "").toUpperCase();
    if (u.includes("RUNNING") || u.includes("OK") || u.includes("NORMAL")) return "ok";
    if (u.includes("ERROR") || u.includes("CRASH") || u.includes("FAIL")) return "err";
    if (u.includes("WARN") || u.includes("HOT") || u.includes("START")) return "warn";
    return "";
  }

  function render() {
    const app = document.getElementById("app");
    if (!app) return;
    app.innerHTML = "";

    if (!state.backendOk && state.screen !== "degraded") {
      state.screen = "degraded";
      state.focus = 0;
    }
    if (state.backendOk && state.snapshot && state.snapshot.setup_complete === false &&
        !["setup", "diagnostics", "degraded"].includes(state.screen)) {
      state.screen = "setup";
      state.focus = 0;
    }

    const top = el("div", "topbar");
    const name =
      (foundation().config && foundation().config.device_name) ||
      (foundation().device_name) ||
      "MineBox";
    top.appendChild(el("div", "brand", name));
    const right = el("div", "");
    right.appendChild(el("div", "clock", new Date().toLocaleTimeString()));
    if (state.stale) right.appendChild(el("div", "stale warn", "STALE DATA"));
    top.appendChild(right);
    app.appendChild(top);

    const screen = el("div", "screen active");
    screen.appendChild(el("h1", "", (SCREENS[state.screen] || SCREENS.home).title));

    if (state.screen === "degraded") {
      const b = el("div", "banner error");
      b.textContent = "Backend unavailable. Showing reconnect UI. Curses fallback: tty1 / minebox-ui.";
      screen.appendChild(b);
    } else if (state.screen === "setup") {
      const b = el("div", "banner");
      b.innerHTML =
        "Setup incomplete. Connect to hotspot <strong>MineBox-Setup</strong> and open " +
        "<strong>http://192.168.4.1</strong> to finish first-boot.";
      screen.appendChild(b);
    } else if (state.message) {
      screen.appendChild(el("div", "banner", state.message));
    }
    if (state.progress) screen.appendChild(el("div", "progress", state.progress));

    if (state.screen === "home" || state.screen === "setup") {
      const m = mc();
      const s = system();
      const net = (state.snapshot && state.snapshot.network) || {};
      screen.appendChild(
        renderStats([
          ["Minecraft", m.value || m.state || m.status || "UNKNOWN", toneForState(m.value || m.state)],
          ["Players", m.players || m.player_count || "0", ""],
          ["CPU temp", formatTemp(s), toneForState(s.thermal_state)],
          ["RAM", formatPct(s.memory_percent || s.memory), ""],
          ["Storage", formatPct(s.disk_percent || s.disk), ""],
          ["Network", netSummary(net), ""],
          ["Hotspot", net.hotspot_ssid || net.hotspot?.ssid || "—", ""],
          ["Local IP", net.ip || net.local_ip || net.addresses?.[0] || "—", ""],
        ])
      );
    }

    if (state.screen === "server" || state.screen === "server_details") {
      const m = mc();
      const health = m.health_check || m.health || {};
      screen.appendChild(
        renderStats([
          ["Name", m.server_name || m.name || "Minecraft", ""],
          ["Provider", m.loader || m.provider || "—", ""],
          ["Version", m.version || "—", ""],
          ["State", m.value || m.state || "—", toneForState(m.value || m.state)],
          ["Uptime", m.uptime || "—", ""],
          ["Players", m.players || "0", ""],
          ["Operation", (foundation().operations && foundation().operations.current) || "idle", ""],
          ["Last error", m.last_error || health.message || "none", m.last_error ? "err" : ""],
        ])
      );
      if (state.screen === "server_details") {
        screen.appendChild(
          renderStats([
            ["Health", health.healthy === true ? "OK" : health.healthy === false ? "UNHEALTHY" : "—", ""],
            ["Support", m.support_level || "see providers", ""],
            ["Crash summary", (foundation().crash && foundation().crash.summary) || "none", ""],
            ["Secrets", "redacted", ""],
          ])
        );
      }
    }

    if (state.screen === "backups") {
      const b = (state.snapshot && state.snapshot.backups) || {};
      const latest = b.latest || {};
      screen.appendChild(
        renderStats([
          ["Latest", latest.filename || "none", ""],
          ["Count", String(b.count ?? 0), ""],
          ["Total size", formatBytes(b.total_size), ""],
          ["Operation", b.busy ? "RUNNING" : "idle", b.busy ? "warn" : "ok"],
        ])
      );
    }

    if (state.screen === "network") {
      const net = (state.snapshot && state.snapshot.network) || {};
      screen.appendChild(
        renderStats([
          ["Hotspot SSID", net.hotspot_ssid || net.hotspot?.ssid || "—", ""],
          ["Hotspot IP", net.hotspot_address || net.hotspot?.address || "192.168.4.1", ""],
          ["Clients", String(net.hotspot_clients ?? net.clients ?? "—"), ""],
          ["Ethernet", net.ethernet || net.ethernet_status || "—", ""],
          ["Wi-Fi uplink", net.wifi || net.wifi_status || "—", ""],
          ["Internet", net.internet || net.internet_status || "—", ""],
          ["Sharing", String(net.internet_sharing_active ?? net.internet_sharing?.active ?? net.internet_sharing ?? "—"), ""],
          ["Remote access", net.remote_access_state || net.remote_access?.state || "DISABLED", ""],
          ["Remote Minecraft", net.remote_minecraft_exposed ? "EXPOSED" : "off", ""],
        ])
      );
    }

    if (state.screen === "system") {
      const s = system();
      const hw = (foundation().hardware || {});
      screen.appendChild(
        renderStats([
          ["CPU temp", formatTemp(s), ""],
          ["Thermal", s.thermal_state || s.thermal || "—", toneForState(s.thermal_state)],
          ["Fan", s.fan_state || s.fan_capability || "NOT_CONFIGURED", ""],
          ["CPU load", formatPct(s.cpu_percent || s.cpu), ""],
          ["RAM", formatPct(s.memory_percent || s.memory), ""],
          ["Disk", formatPct(s.disk_percent || s.disk), ""],
          ["Uptime", s.uptime || "—", ""],
          ["Version", foundation().version || "—", ""],
          ["Profile", hw.profile || "—", ""],
          ["Unresolved", unresolvedSummary(hw), "warn"],
        ])
      );
    }

    if (state.screen === "confirm") {
      const box = el("div", "confirm-box");
      box.appendChild(el("h2", "", "Confirm action"));
      box.appendChild(el("p", "", state.confirmLabel || state.confirmAction || ""));
      box.appendChild(el("p", "", "Rotate to choose · Press to select · Long-press to cancel"));
      screen.appendChild(box);
    }

    if (state.screen === "diagnostics") {
      const live = state.liveInputs;
      const hw = (state.snapshot && state.snapshot.hardware_diag) || {};
      const grid = el("div", "diag-grid");
      grid.appendChild(diagRow("Left button", live.left));
      grid.appendChild(diagRow("Right button", live.right));
      grid.appendChild(diagRow("Encoder press", live.enc));
      const rot = el("div", "stat");
      rot.appendChild(el("div", "label", "Encoder event"));
      rot.appendChild(el("div", "value", live.deltaHint || "—"));
      grid.appendChild(rot);
      grid.appendChild(statText("LED capability", "NOT_CONFIGURED"));
      grid.appendChild(statText("Fan capability", "NOT_CONFIGURED"));
      grid.appendChild(statText("Profile", (hw.snapshot && hw.snapshot.profile) || hw.profile || "—"));
      grid.appendChild(statText("Pin verification", (hw.snapshot && hw.snapshot.gpio_verification) || "see hardware.toml"));
      screen.appendChild(grid);
      screen.appendChild(el("div", "banner", "Diagnostics does not trigger server or power actions."));
    }

    const menu = el("div", "menu");
    const items = currentItems();
    clampFocus();
    items.forEach((item, idx) => {
      const row = el("div", "item" + (idx === state.focus ? " focused" : ""));
      row.appendChild(el("span", "", item.label));
      if (idx === state.focus) row.appendChild(el("span", "hint", "◀ focus"));
      menu.appendChild(row);
    });
    screen.appendChild(menu);

    const footer = el("div", "footer");
    footer.appendChild(el("span", "", "Encoder: turn=move · press=select · hold=back"));
    footer.appendChild(el("span", "", "Buttons: short=move · hold L=back · hold R=select"));
    screen.appendChild(footer);
    app.appendChild(screen);
  }

  function diagRow(label, on) {
    const box = el("div", "stat");
    box.appendChild(el("div", "label", label));
    const pill = el("span", "pill " + (on ? "on" : "off"), on ? "ACTIVE" : "idle");
    box.appendChild(pill);
    return box;
  }
  function statText(label, value) {
    const box = el("div", "stat");
    box.appendChild(el("div", "label", label));
    box.appendChild(el("div", "value", value));
    return box;
  }
  function formatTemp(s) {
    const t = s.temperature_c ?? s.cpu_temp_c ?? s.temp_c;
    return t == null ? "—" : Number(t).toFixed(1) + "°C";
  }
  function formatPct(v) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(0) + "%" : String(v);
  }
  function formatBytes(n) {
    const v = Number(n || 0);
    if (v < 1024) return v + " B";
    if (v < 1024 * 1024) return (v / 1024).toFixed(1) + " KB";
    return (v / (1024 * 1024)).toFixed(1) + " MB";
  }
  function netSummary(net) {
    return net.summary || net.state || net.mode || "see Network";
  }
  function unresolvedSummary(hw) {
    const feats = hw.features || {};
    const bad = Object.entries(feats)
      .filter(([, v]) => String(v).includes("NOT_CONFIGURED"))
      .map(([k]) => k);
    return bad.length ? bad.slice(0, 3).join(", ") : "none listed";
  }

  async function ensureSession() {
    try {
      await fetch("/api/v1/display/session", { method: "POST", credentials: "same-origin" });
    } catch (_) {
      /* ignore — degraded mode will show */
    }
  }

  async function refresh(force) {
    try {
      const res = await fetch("/api/v1/display/snapshot", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!res.ok) throw new Error("snapshot " + res.status);
      const data = await res.json();
      state.snapshot = data;
      state.stale = !!data.stale;
      state.actionMap = data.action_map || state.actionMap;
      state.backendOk = true;
      state.lastOkAt = Date.now();
      state.retryDelay = 1000;
      if (state.screen === "degraded") go(data.setup_complete ? "home" : "setup");
      render();
    } catch (err) {
      state.backendOk = false;
      state.stale = true;
      state.retryDelay = Math.min(RETRY_MAX_MS, state.retryDelay * 1.5);
      if (force || state.screen !== "degraded") go("degraded");
      render();
    }
  }

  async function pollEvents() {
    try {
      const q = state.diagnosticsMode ? "?diagnostics=1" : "";
      const res = await fetch("/api/v1/display/events" + q, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!res.ok) return;
      const data = await res.json();
      state.actionMap = data.map || state.actionMap;
      for (const ev of data.events || []) {
        applyEvent(ev.type);
      }
      if (state.diagnosticsMode) {
        // Clear momentary pills shortly after.
        setTimeout(() => {
          state.liveInputs.left = false;
          state.liveInputs.right = false;
          state.liveInputs.enc = false;
          if (state.diagnosticsMode) render();
        }, 350);
      }
    } catch (_) {
      /* ignore */
    }
  }

  function bindKeyboard() {
    window.addEventListener("keydown", (e) => {
      const key = e.key;
      if (["ArrowRight", "ArrowDown", "d", "D"].includes(key)) {
        e.preventDefault();
        applyEvent("ENCODER_CW");
      } else if (["ArrowLeft", "ArrowUp", "a", "A"].includes(key)) {
        e.preventDefault();
        applyEvent("ENCODER_CCW");
      } else if (key === "Enter") {
        e.preventDefault();
        applyEvent("ENCODER_PRESS");
      } else if (key === "Escape" || key === "Backspace") {
        e.preventDefault();
        applyEvent("LEFT_BUTTON_PRESS");
      } else if (key === "Home" || key === "h" || key === "H") {
        e.preventDefault();
        applyEvent("LEFT_BUTTON_HOLD");
      } else if (key === "[") {
        e.preventDefault();
        applyEvent("LEFT_BUTTON_PRESS");
      } else if (key === "{") {
        e.preventDefault();
        applyEvent("LEFT_BUTTON_HOLD");
      } else if (key === "]") {
        e.preventDefault();
        applyEvent("RIGHT_BUTTON_PRESS");
      } else if (key === "}") {
        e.preventDefault();
        applyEvent("RIGHT_BUTTON_HOLD");
      }
    });
  }

  async function boot() {
    if (document.body.dataset.dev === "1") document.body.classList.add("dev-mode");
    await ensureSession();
    await refresh(true);
    bindKeyboard();
    setInterval(() => refresh(false), POLL_MS);
    setInterval(pollEvents, EVENT_MS);
    setInterval(() => {
      const clock = document.querySelector(".clock");
      if (clock) clock.textContent = new Date().toLocaleTimeString();
    }, 1000);
  }

  window.MineBoxDisplay = {
    state,
    go,
    applyEvent,
    refresh,
    currentItems,
    intentNext,
    intentPrev,
    intentBack,
    intentHome,
    intentContext,
    intentPower,
    intentSelect,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
