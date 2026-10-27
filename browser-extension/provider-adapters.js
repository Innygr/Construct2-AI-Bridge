(function (root) {
  "use strict";

  // Dedicated site adapters are loaded before this registry in the extension popup.
  // CommonJS loading keeps the same adapters testable with Node.js.
  let chatgpt = root.C2AIChatGPTConnector;
  let claude = root.C2AIClaudeConnector;
  if (typeof module !== "undefined" && module.exports && typeof require === "function") {
    chatgpt = chatgpt || require("./connectors/chatgpt.js");
    claude = claude || require("./connectors/claude.js");
  }

  function matchesHost(hostname, domain) {
    const host = String(hostname || "").toLowerCase().replace(/\.$/, "");
    return host === domain || host.endsWith("." + domain);
  }

  function detectProvider(hostname) {
    if (chatgpt?.matchesHost(hostname)) return "ChatGPT";
    if (claude?.matchesHost(hostname)) return "Claude";
    if (matchesHost(hostname, "gemini.google.com")) return "Gemini";
    return "Other / unsupported site";
  }

  function getConnector(hostname) {
    const provider = detectProvider(hostname);
    if (provider === "ChatGPT") return chatgpt;
    if (provider === "Claude") return claude;
    if (provider === "Gemini") return Object.freeze({
      id: "gemini", label: "Gemini",
      composerSelectors: Object.freeze(['rich-textarea [contenteditable="true"]', 'div[contenteditable="true"]', "textarea"]),
      replySelectors: Object.freeze(["message-content .markdown", "model-response .markdown", ".model-response-text"]),
      fillStrategy: "contenteditable"
    });
    return Object.freeze({
      id: "generic", label: "Other / unsupported site",
      composerSelectors: Object.freeze(["textarea:not([disabled])", '[contenteditable="true"]:not([aria-disabled="true"])']),
      replySelectors: Object.freeze([]), fillStrategy: "generic"
    });
  }

  function getComposerSelectors(hostname) { return [...getConnector(hostname).composerSelectors]; }
  function getReplySelectors(hostname) { return [...getConnector(hostname).replySelectors]; }

  const adapters = Object.freeze({ detectProvider, getConnector, getComposerSelectors, getReplySelectors });
  if (typeof module !== "undefined" && module.exports) module.exports = adapters;
  root.C2AIBridgeAdapters = adapters;
})(typeof globalThis !== "undefined" ? globalThis : this);
