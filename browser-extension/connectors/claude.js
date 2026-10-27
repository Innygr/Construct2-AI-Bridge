(function (root) {
  "use strict";
  const connector = Object.freeze({
    id: "claude",
    label: "Claude",
    matchesHost(host) {
      const value = String(host || "").toLowerCase().replace(/\.$/, "");
      return value === "claude.ai" || value.endsWith(".claude.ai");
    },
    composerSelectors: Object.freeze([
      '[contenteditable="true"][data-placeholder]',
      'div[contenteditable="true"][role="textbox"]',
      'fieldset [contenteditable="true"]',
      'fieldset textarea'
    ]),
    replySelectors: Object.freeze([
      '[data-testid="chat-message"]',
      '.font-claude-message',
      '[data-testid*="conversation-turn"]'
    ]),
    fillStrategy: "contenteditable"
  });
  if (typeof module !== "undefined" && module.exports) module.exports = connector;
  root.C2AIClaudeConnector = connector;
})(typeof globalThis !== "undefined" ? globalThis : this);
