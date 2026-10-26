"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const adapters = require("../provider-adapters.js");

test("detects supported providers by exact host or subdomain", () => {
  assert.equal(adapters.detectProvider("chatgpt.com"), "ChatGPT");
  assert.equal(adapters.detectProvider("chat.openai.com"), "ChatGPT");
  assert.equal(adapters.detectProvider("work.chatgpt.com"), "ChatGPT");
  assert.equal(adapters.detectProvider("claude.ai"), "Claude");
  assert.equal(adapters.detectProvider("teams.claude.ai"), "Claude");
  assert.equal(adapters.detectProvider("gemini.google.com"), "Gemini");
  assert.equal(adapters.detectProvider("labs.gemini.google.com"), "Gemini");
});

test("does not classify lookalike or unrelated hosts as supported providers", () => {
  assert.equal(adapters.detectProvider("chatgpt.com.attacker.example"), "Other / unsupported site");
  assert.equal(adapters.detectProvider("notclaude.ai"), "Other / unsupported site");
  assert.equal(adapters.detectProvider("gemini.google.com.example.org"), "Other / unsupported site");
  assert.equal(adapters.detectProvider("example.org"), "Other / unsupported site");
});

test("returns provider-specific composer selectors and safe generic fallbacks", () => {
  assert.deepEqual(adapters.getComposerSelectors("chatgpt.com"), ['#prompt-textarea', '[data-testid="prompt-textarea"]', 'main form [contenteditable="true"]']);
  assert.deepEqual(adapters.getComposerSelectors("claude.ai"), ['[contenteditable="true"][data-placeholder]', 'div[contenteditable="true"]', 'fieldset textarea']);
  assert.deepEqual(adapters.getComposerSelectors("gemini.google.com"), ['rich-textarea [contenteditable="true"]', 'div[contenteditable="true"]', 'textarea']);
  assert.deepEqual(adapters.getComposerSelectors("example.org"), ['textarea:not([disabled])', '[contenteditable="true"]:not([aria-disabled="true"])']);
});

test("returns provider-specific reply selectors and empty generic fallback", () => {
  assert.deepEqual(adapters.getReplySelectors("chatgpt.com"), ['[data-message-author-role="assistant"]']);
  assert.deepEqual(adapters.getReplySelectors("claude.ai"), ['[data-testid="chat-message"]', '.font-claude-message']);
  assert.deepEqual(adapters.getReplySelectors("gemini.google.com"), ['message-content .markdown', 'model-response .markdown', '.model-response-text']);
  assert.deepEqual(adapters.getReplySelectors("example.org"), []);
});
