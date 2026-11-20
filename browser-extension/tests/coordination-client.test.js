"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  normalizeApiBase,
  normalizeLockPath,
  createClient
} = require("../coordination-client.js");

test("normalizes loopback URLs and removes a trailing slash", () => {
  assert.equal(normalizeApiBase("http://127.0.0.1:8765/"), "http://127.0.0.1:8765");
  assert.equal(normalizeApiBase("http://localhost:9000"), "http://localhost:9000");
});

test("rejects non-loopback and non-HTTP bridge addresses", () => {
  for (const value of [
    "https://127.0.0.1:8765",
    "http://192.168.1.20:8765",
    "http://example.com",
    "http://user:pass@127.0.0.1:8765",
    "http://127.0.0.1:8765/api"
  ]) {
    assert.throws(() => normalizeApiBase(value));
  }
});

test("client keeps requests on the configured origin and blocks redirects", async () => {
  const calls = [];
  const client = createClient("http://127.0.0.1:8765", async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ tasks: [] }) };
  });

  assert.deepEqual(await client.request("/api/coordination/tasks"), { tasks: [] });
  assert.equal(calls[0].url, "http://127.0.0.1:8765/api/coordination/tasks");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.equal(calls[0].options.redirect, "error");
  assert.equal(calls[0].options.credentials, "omit");
});

test("client reports API error details", async () => {
  const client = createClient("http://localhost:8765", async () => ({
    ok: false,
    status: 409,
    json: async () => ({ detail: "Task is already owned." })
  }));
  await assert.rejects(client.request("/api/coordination/tasks"), /Task is already owned/);
});

test("client rejects paths that could escape the configured bridge route", () => {
  const client = createClient("http://127.0.0.1:8765", async () => ({ ok: true, json: async () => ({}) }));
  assert.throws(() => client.url("//example.com/path"));
  assert.throws(() => client.url("https://example.com/path"));
  assert.throws(() => client.url("/api\\coordination"));
});

test("normalizes project-relative lock paths and rejects traversal", () => {
  assert.equal(normalizeLockPath("src\\parser.py"), "src/parser.py");
  assert.equal(normalizeLockPath("src/parser.py"), "src/parser.py");
  for (const value of ["", "/etc/passwd", "../server.py", "src/../server.py", "src//server.py", "src/./server.py"]) {
    assert.throws(() => normalizeLockPath(value));
  }
});

test("task helpers use the documented list, claim, and PATCH contracts", async () => {
  const calls = [];
  const client = createClient("http://127.0.0.1:8765", async (url, options) => {
    calls.push({ url, options });
    if (options.method === "PATCH") return { ok: true, json: async () => ({ task: { id: "C2-12345678", status: "in_review" } }) };
    if (options.method === "POST") return { ok: true, json: async () => ({ task: { id: "C2-12345678", owner: "chatgpt" } }) };
    return { ok: true, json: async () => ({ tasks: [{ id: "C2-12345678" }] }) };
  });

  assert.equal((await client.listTasks("open"))[0].id, "C2-12345678");
  assert.equal((await client.claimTask("C2-12345678", "chatgpt", "chatgpt/extension")).owner, "chatgpt");
  assert.equal((await client.updateTask("C2-12345678", "chatgpt", "in_review", "chatgpt/extension")).status, "in_review");
  assert.equal(calls[0].url, "http://127.0.0.1:8765/api/coordination/tasks?status=open");
  assert.deepEqual(JSON.parse(calls[1].options.body), { agent: "chatgpt", branch: "chatgpt/extension" });
  assert.equal(calls[2].options.method, "PATCH");
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    agent: "chatgpt", status: "in_review", branch: "chatgpt/extension"
  });
  await assert.rejects(client.updateTask("C2-12345678", "chatgpt", "unknown"), /Unsupported task status/);
});

test("message helper follows the documented response envelope", async () => {
  const calls = [];
  const client = createClient("http://127.0.0.1:8765", async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({
      messages: [{ id: 8, body: "hello" }],
      message: { id: 9, body: "posted" }
    }) };
  });
  assert.equal((await client.listMessages(7, 50))[0].id, 8);
  assert.equal((await client.postMessage("chatgpt", "posted")).id, 9);
  assert.match(calls[0].url, /after_id=7&limit=50/);
  assert.deepEqual(JSON.parse(calls[1].options.body), { agent: "chatgpt", body: "posted" });
});

test("lock helpers keep list tokens private and use exact release payloads", async () => {
  const calls = [];
  const client = createClient("http://127.0.0.1:8765", async (url, options) => {
    calls.push({ url, options });
    if (options.method === "POST") {
      return { ok: true, json: async () => ({ lock: {
        path: "src/parser.py", agent: "chatgpt", token: "private-token", expires_at: 1234
      } }) };
    }
    if (options.method === "DELETE") return { ok: true, json: async () => ({ released: true }) };
    return { ok: true, json: async () => ({ locks: [
      { path: "src/parser.py", agent: "chatgpt", token: "must-not-be-rendered", expires_at: 1234 }
    ] }) };
  });

  const locks = await client.listLocks();
  assert.deepEqual(locks, [{ path: "src/parser.py", agent: "chatgpt", expires_at: 1234 }]);
  const lock = await client.acquireLock("src\\parser.py", "chatgpt", "C2-12345678", 600);
  assert.equal(lock.token, "private-token");
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    path: "src/parser.py", agent: "chatgpt", task_id: "C2-12345678", ttl_seconds: 600
  });
  assert.deepEqual(await client.releaseLock(lock.path, "chatgpt", lock.token), { released: true });
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    path: "src/parser.py", agent: "chatgpt", token: "private-token"
  });
  await assert.rejects(client.acquireLock("src/a.py", "chatgpt", null, 10), /30 and 86400/);
});
