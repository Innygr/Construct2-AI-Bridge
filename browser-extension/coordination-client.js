(function (root) {
  "use strict";

  function normalizeApiBase(value) {
    const parsed = new URL(String(value || "").trim());
    if (parsed.protocol !== "http:" ||
        !["127.0.0.1", "localhost"].includes(parsed.hostname) ||
        parsed.username || parsed.password || parsed.search || parsed.hash ||
        (parsed.pathname !== "/" && parsed.pathname !== "")) {
      throw new Error("Use a loopback HTTP address only (127.0.0.1 or localhost).");
    }
    return parsed.origin;
  }

  function createClient(baseUrl, fetchImpl) {
    const requestFetch = fetchImpl || root.fetch.bind(root);
    let base = normalizeApiBase(baseUrl);

    return Object.freeze({
      get baseUrl() { return base; },
      setBase(value) { base = normalizeApiBase(value); return base; },
      url(path) {
        if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) {
          throw new Error("API paths must be absolute paths on the configured bridge origin.");
        }
        return base + path;
      },
      async request(path, options) {
        const response = await requestFetch(this.url(path), {
          ...(options || {}),
          headers: { "Content-Type": "application/json", ...((options && options.headers) || {}) }
        });
        let data = {};
        try { data = await response.json(); } catch {}
        if (!response.ok) {
          const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
          throw new Error(detail || ("HTTP " + response.status));
        }
        return data;
      }
    });
  }

  const clientApi = Object.freeze({ normalizeApiBase, createClient });
  if (typeof module !== "undefined" && module.exports) module.exports = clientApi;
  root.C2AICoordinationClient = clientApi;
})(typeof globalThis !== "undefined" ? globalThis : this);
