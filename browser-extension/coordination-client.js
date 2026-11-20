(function (root) {
  "use strict";

  const TASK_STATUSES = Object.freeze(["open", "claimed", "in_review", "done", "blocked"]);

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

  function requiredText(value, label, maxLength) {
    const normalized = String(value == null ? "" : value).trim();
    if (!normalized) throw new Error(label + " is required.");
    if (normalized.length > maxLength) throw new Error(label + " must be " + maxLength + " characters or fewer.");
    return normalized;
  }

  function normalizeLockPath(value) {
    const normalized = requiredText(value, "Project-relative path", 1024).replace(/\\/g, "/");
    const parts = normalized.split("/");
    if (normalized.startsWith("/") || /^[A-Za-z]:/.test(normalized) ||
        /[\u0000-\u001f\u007f]/.test(normalized) ||
        parts.some(part => !part || part === "." || part === "..")) {
      throw new Error("Use a safe project-relative path (no absolute paths, empty segments, or . / .. segments).");
    }
    return parts.join("/");
  }

  function createClient(baseUrl, fetchImpl) {
    const requestFetch = fetchImpl || root.fetch.bind(root);
    let base = normalizeApiBase(baseUrl);

    async function request(path, options) {
      const response = await requestFetch(client.url(path), {
        ...(options || {}),
        // The bridge has no cross-origin redirect use case. Do not forward a
        // locally entered coordination payload to a redirect destination.
        redirect: "error",
        credentials: "omit",
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

    const client = {
      get baseUrl() { return base; },
      setBase(value) { base = normalizeApiBase(value); return base; },
      url(path) {
        if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//") ||
            path.includes("\\") || /[\u0000-\u001f\u007f]/.test(path)) {
          throw new Error("API paths must be absolute paths on the configured bridge origin.");
        }
        const resolved = new URL(path, base);
        if (resolved.origin !== base || !resolved.pathname.startsWith("/api/")) {
          throw new Error("API requests must stay under the configured bridge origin's /api/ route.");
        }
        return resolved.href;
      },
      request,

      async listTasks(status) {
        if (status && !TASK_STATUSES.includes(status)) throw new Error("Unsupported task status.");
        const data = await request("/api/coordination/tasks" + (status ? "?status=" + encodeURIComponent(status) : ""));
        if (!Array.isArray(data.tasks)) throw new Error("The bridge returned an invalid task list.");
        return data.tasks;
      },

      async claimTask(taskId, agent, branch) {
        const id = requiredText(taskId, "Task ID", 40);
        const who = requiredText(agent, "Agent", 80);
        const body = { agent: who };
        if (branch != null && String(branch).trim()) body.branch = requiredText(branch, "Git branch", 200);
        const data = await request("/api/coordination/tasks/" + encodeURIComponent(id) + "/claim", {
          method: "POST", body: JSON.stringify(body)
        });
        if (!data.task) throw new Error("The bridge did not return the claimed task.");
        return data.task;
      },

      async updateTask(taskId, agent, status, branch) {
        const id = requiredText(taskId, "Task ID", 40);
        const who = requiredText(agent, "Agent", 80);
        if (!TASK_STATUSES.includes(status)) throw new Error("Unsupported task status.");
        const body = { agent: who, status };
        if (branch != null && String(branch).trim()) body.branch = requiredText(branch, "Git branch", 200);
        const data = await request("/api/coordination/tasks/" + encodeURIComponent(id), {
          method: "PATCH", body: JSON.stringify(body)
        });
        if (!data.task) throw new Error("The bridge did not return the updated task.");
        return data.task;
      },

      async listMessages(afterId, limit, taskId) {
        const after = Number.isInteger(afterId) && afterId >= 0 ? afterId : 0;
        const count = Number.isInteger(limit) && limit >= 1 && limit <= 500 ? limit : 100;
        const params = new URLSearchParams({ after_id: String(after), limit: String(count) });
        if (taskId) params.set("task_id", requiredText(taskId, "Task ID", 40));
        const data = await request("/api/coordination/messages?" + params.toString());
        if (!Array.isArray(data.messages)) throw new Error("The bridge returned an invalid message list.");
        return data.messages;
      },

      async postMessage(agent, body, taskId) {
        const payload = {
          agent: requiredText(agent, "Agent", 80),
          body: requiredText(body, "Message", 12000)
        };
        if (taskId) payload.task_id = requiredText(taskId, "Task ID", 40);
        const data = await request("/api/coordination/messages", {
          method: "POST", body: JSON.stringify(payload)
        });
        if (!data.message) throw new Error("The bridge did not return the posted message.");
        return data.message;
      },

      async listLocks() {
        const data = await request("/api/coordination/locks");
        if (!Array.isArray(data.locks)) throw new Error("The bridge returned an invalid lock list.");
        // Never expose lock tokens to the popup renderer.
        return data.locks.map(({ token, ...lock }) => lock);
      },

      async acquireLock(path, agent, taskId, ttlSeconds) {
        const ttl = ttlSeconds == null ? 900 : Number(ttlSeconds);
        if (!Number.isInteger(ttl) || ttl < 30 || ttl > 86400) {
          throw new Error("Lock duration must be an integer from 30 to 86400 seconds.");
        }
        const payload = {
          path: normalizeLockPath(path),
          agent: requiredText(agent, "Agent", 80),
          ttl_seconds: ttl
        };
        if (taskId) payload.task_id = requiredText(taskId, "Task ID", 40);
        const data = await request("/api/coordination/locks", {
          method: "POST", body: JSON.stringify(payload)
        });
        if (!data.lock || typeof data.lock.token !== "string" || !data.lock.token) {
          throw new Error("The bridge did not return a usable lock token.");
        }
        return data.lock;
      },

      async releaseLock(path, agent, token) {
        const payload = {
          path: normalizeLockPath(path),
          agent: requiredText(agent, "Agent", 80),
          token: requiredText(token, "Lock token", 64)
        };
        return request("/api/coordination/locks", {
          method: "DELETE", body: JSON.stringify(payload)
        });
      }
    };

    return Object.freeze(client);
  }

  const clientApi = Object.freeze({ normalizeApiBase, normalizeLockPath, createClient, TASK_STATUSES });
  if (typeof module !== "undefined" && module.exports) module.exports = clientApi;
  root.C2AICoordinationClient = clientApi;
})(typeof globalThis !== "undefined" ? globalThis : this);
