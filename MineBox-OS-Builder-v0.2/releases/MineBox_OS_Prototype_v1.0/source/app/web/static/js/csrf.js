/* MineBox CSRF helper — attach X-CSRF-Token to mutating fetch calls. */
(function () {
  function readCookieToken() {
    // Prefer meta tag / global set by pages.
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    if (window.MINEBOX_CSRF_TOKEN) return window.MINEBOX_CSRF_TOKEN;
    return "";
  }

  async function refreshToken() {
    try {
      const response = await fetch("/api/v1/auth/csrf", {
        credentials: "same-origin",
      });
      if (!response.ok) return readCookieToken();
      const data = await response.json();
      if (data && data.csrf_token) {
        window.MINEBOX_CSRF_TOKEN = data.csrf_token;
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) meta.content = data.csrf_token;
        return data.csrf_token;
      }
    } catch (_err) {
      /* ignore */
    }
    return readCookieToken();
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    init = init || {};
    const method = (init.method || "GET").toUpperCase();
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      const headers = new Headers(init.headers || {});
      if (!headers.has("X-CSRF-Token")) {
        let token = readCookieToken();
        if (!token) token = await refreshToken();
        if (token) headers.set("X-CSRF-Token", token);
      }
      init.headers = headers;
      init.credentials = init.credentials || "same-origin";
    }
    const response = await originalFetch(input, init);
    const fresh = response.headers.get("X-CSRF-Token");
    if (fresh) {
      window.MINEBOX_CSRF_TOKEN = fresh;
      const meta = document.querySelector('meta[name="csrf-token"]');
      if (meta) meta.content = fresh;
    }
    return response;
  };

  window.MineBoxCSRF = { refreshToken, readCookieToken };
})();
