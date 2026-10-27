(function (root) {
  "use strict";
  const connector = Object.freeze({
    id: "chatgpt",
    label: "ChatGPT",
    matchesHost(host) {
      const value = String(host || "").toLowerCase().replace(/\.$/, "");
      return value === "chatgpt.com" || value.endsWith(".chatgpt.com") || value === "chat.openai.com";
    },
    composerSelectors: Object.freeze([
      "#prompt-textarea",
      '[data-testid="prompt-textarea"]',
      'form [contenteditable="true"][role="textbox"]',
      'main [contenteditable="true"][role="textbox"]'
    ]),
    replySelectors: Object.freeze([
      '[data-message-author-role="assistant"]',
      '[data-testid="conversation-turn"] [data-message-author-role="assistant"]'
    ]),
    fillStrategy: "contenteditable"
  });
  if (typeof module !== "undefined" && module.exports) module.exports = connector;
  root.C2AIChatGPTConnector = connector;
})(typeof globalThis !== "undefined" ? globalThis : this);
