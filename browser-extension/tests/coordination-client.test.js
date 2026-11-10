"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { normalizeApiBase, createClient } = require("../coordination-client.js");

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

test("client keeps requests on the configured origin", async () => {
  const calls = [];
  const client = createClient("http://127.0.0.1:8765", async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ tasks: [] }) };
  });

  assert.deepEqual(await client.request("/api/coordination/tasks"), { tasks: [] });
  assert.equal(calls[0].url, "http://127.0.0.1:8765/api/coordination/tasks");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
});

test("client reports API error details", async () => {
  const client = createClient("http://localhost:8765", async () => ({
    ok: false,
    status: 409,
    json: async () => ({ detail: "Task is already owned." })
  }));
  await assert.rejects(client.request("/api/coordination/tasks"), /Task is already owned/);
});

test("client rejects paths that could escape the configured origin", () => {
  const client = createClient("http://127.0.0.1:8765", async () => ({ ok: true, json: async () => ({}) }));
  assert.throws(() => client.url("//example.com/path"));
  assert.throws(() => client.url("https://example.com/path"));
});
