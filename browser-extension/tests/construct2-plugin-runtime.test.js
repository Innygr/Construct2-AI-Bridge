const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const runtimePath = path.join(__dirname, "../../construct2-plugin/AI_Bridge/runtime.js");
const runtimeSource = fs.readFileSync(runtimePath, "utf8");

test("Construct 2 SendToBrowserAI queues a tagged request and receives its browser reply", async () => {
  const calls = [];
  class FakeXHR {
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader() {}
    send(body) {
      this.body = body || null;
      calls.push(this);
      setImmediate(() => {
        this.readyState = 4;
        this.status = 200;
        if (this.method === "POST" && this.url.endsWith("/api/ai/requests")) {
          this.responseText = JSON.stringify({ request: { id: "AI-ABCDEF123456" } });
        } else if (this.url.endsWith("/api/ai/requests/AI-ABCDEF123456")) {
          this.responseText = JSON.stringify({
            request: {
              id: "AI-ABCDEF123456",
              status: "completed",
              provider: "chatgpt",
              claimed_provider: "chatgpt",
              response: "The event condition is reversed."
            }
          });
        } else {
          this.status = 404;
          this.responseText = JSON.stringify({ detail: "Not found" });
        }
        if (this.onreadystatechange) this.onreadystatechange();
      });
    }
    abort() {
      this.readyState = 4;
      if (this.onabort) this.onabort();
    }
  }

  const triggered = [];
  const windowStub = {
    C2AIBridge: {
      normalizeBaseURL(value) {
        return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(value) ? value : "";
      },
      safeJSON(value) {
        try { return JSON.parse(value); } catch { return null; }
      }
    },
    setTimeout,
    clearTimeout
  };
  const cr = {
    plugins_: {},
    equals_nocase(a, b) { return String(a).toLowerCase() === String(b).toLowerCase(); }
  };
  const sandbox = {
    window: windowStub,
    cr,
    assert2(condition, message) { if (!condition) throw new Error(message); },
    XMLHttpRequest: FakeXHR,
    setTimeout,
    clearTimeout,
    Date,
    JSON,
    encodeURIComponent
  };
  vm.runInNewContext(runtimeSource, sandbox, { filename: runtimePath });

  const Plugin = cr.plugins_.AIBridge;
  const plugin = new Plugin({ trigger(condition, instance) { triggered.push(condition); } });
  const type = new Plugin.prototype.Type(plugin);
  const instance = new Plugin.prototype.Instance(type);
  instance.properties = [];
  instance.projectContext = "PROJECT CONTEXT";
  instance.onCreate();

  Plugin.prototype.acts.SendToBrowserAI.call(
    instance, "event-debug", 1, "Find the bug", "Act as a debugger", 1
  );

  await new Promise(resolve => setTimeout(resolve, 40));

  const createCall = calls.find(call => call.method === "POST");
  assert.ok(createCall, "the plugin should POST a browser AI request");
  const payload = JSON.parse(createCall.body);
  assert.equal(payload.provider, "chatgpt");
  assert.match(payload.prompt, /Find the bug/);
  assert.match(payload.prompt, /PROJECT CONTEXT/);
  assert.equal(payload.system, "Act as a debugger");

  assert.equal(instance.lastRequestID, "AI-ABCDEF123456");
  assert.equal(instance.lastResponse, "The event condition is reversed.");
  assert.equal(instance.lastTag, "event-debug");
  assert.equal(instance.selectedModel, "browser:chatgpt");
  assert.ok(triggered.includes(Plugin.prototype.cnds.OnAIResponse));
  assert.equal(Plugin.prototype.cnds.OnAIResponse.call(instance, "event-debug"), true);
  assert.equal(Plugin.prototype.cnds.OnAIResponse.call(instance, "other-tag"), false);
});
