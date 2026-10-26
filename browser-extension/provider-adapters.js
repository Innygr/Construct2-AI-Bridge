(function (root) {
  "use strict";

  function matchesHost(hostname, domain) {
    const host = String(hostname || "").toLowerCase().replace(/\.$/, "");
    return host === domain || host.endsWith("." + domain);
  }

  function detectProvider(hostname) {
    if (matchesHost(hostname, "chatgpt.com") || String(hostname || "").toLowerCase() === "chat.openai.com") return "ChatGPT";
    if (matchesHost(hostname, "claude.ai")) return "Claude";
    if (matchesHost(hostname, "gemini.google.com")) return "Gemini";
    return "Other / unsupported site";
  }

  function getComposerSelectors(hostname) {
    const provider = detectProvider(hostname);
    if (provider === "ChatGPT") return ['#prompt-textarea', '[data-testid="prompt-textarea"]', 'main form [contenteditable="true"]'];
    if (provider === "Claude") return ['[contenteditable="true"][data-placeholder]', 'div[contenteditable="true"]', 'fieldset textarea'];
    if (provider === "Gemini") return ['rich-textarea [contenteditable="true"]', 'div[contenteditable="true"]', 'textarea'];
    return ['textarea:not([disabled])', '[contenteditable="true"]:not([aria-disabled="true"])'];
  }

  function getReplySelectors(hostname) {
    const provider = detectProvider(hostname);
    if (provider === "ChatGPT") return ['[data-message-author-role="assistant"]'];
    if (provider === "Claude") return ['[data-testid="chat-message"]', '.font-claude-message'];
    if (provider === "Gemini") return ['message-content .markdown', 'model-response .markdown', '.model-response-text'];
    return [];
  }

  const adapters = Object.freeze({ detectProvider, getComposerSelectors, getReplySelectors });
  if (typeof module !== "undefined" && module.exports) module.exports = adapters;
  root.C2AIBridgeAdapters = adapters;
})(typeof globalThis !== "undefined" ? globalThis : this);
