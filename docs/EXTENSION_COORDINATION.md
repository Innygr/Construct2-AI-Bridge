# Browser extension coordination panel

The extension popup includes an optional coordination panel for the local bridge.

## Connection

The default bridge address is `http://127.0.0.1:8765`. The popup remembers a custom address in browser-local extension storage, but accepts loopback HTTP addresses only (`127.0.0.1` or `localhost`). Keep the bridge bound to loopback; do not expose its unauthenticated coordination API to a LAN or the public internet.

The popup reads open tasks from `GET /api/coordination/tasks?status=open` and messages from `GET /api/coordination/messages?after_id=<id>&limit=100`. It refreshes every 12 seconds while the popup is open and stops polling when the popup is closed.

## User-controlled actions

- **Refresh** reloads open tasks and new messages.
- **Claim task** sends the selected agent label and the extension branch name to the task claim endpoint.
- **Post message** sends only the text entered in the coordination message box, the selected agent label, and an optional selected task ID.
- The agent label is a coordination label, not authentication. Use the identity belonging to the agent actually operating the extension; do not impersonate another agent.

The coordination panel does not send provider conversation contents, captured replies, prompts, selected event-sheet XML, or project files to the coordination API. Existing prompt-fill and reply-capture actions remain user-triggered.

## Manual smoke test

1. Start the bridge locally and load the unpacked extension from `browser-extension/`.
2. Open the extension popup. Confirm the status reports a connection and open tasks appear.
3. Claim an unclaimed test task. Confirm the bridge task board records the agent and branch.
4. Post a short message with and without a task selected. Confirm both appear in the bridge message feed and extension popup.
5. Close and reopen the popup. Confirm the saved bridge address and agent label persist.
6. Stop the bridge and refresh. Confirm the popup reports an unavailable bridge without breaking the rest of the popup.
7. Try a non-loopback address in the bridge field. Confirm the popup rejects it before saving.

The smoke test must be run against the actual local bridge; GitHub-side commits alone do not verify local connectivity or browser permissions.
