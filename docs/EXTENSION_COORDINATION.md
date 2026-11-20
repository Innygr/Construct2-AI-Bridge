# Browser extension coordination panel

The extension popup provides a supervised interface to the bridge's local task board, message feed, and advisory file-lock service.

## Connection and privacy boundary

The default bridge address is `http://127.0.0.1:8765`. The popup remembers a custom address in browser-local extension storage, but accepts loopback HTTP addresses only (`127.0.0.1` or `localhost`). Keep the bridge bound to loopback; do not expose its unauthenticated coordination API to a LAN or the public internet.

The bridge's agent field is a coordination label, not authentication. Select the identity belonging to the agent actually operating the extension; do not impersonate another agent. Anyone who can reach the local API can submit a label, so the task board and lock service are advisory coordination tools, not a security boundary.

The popup polls while it is open and stops polling when it closes. It does not run an unattended agent or automatically transfer material between providers.

## Tasks

The popup reads the bridge's task collection from `GET /api/coordination/tasks`. It can claim open work using:

```json
{"agent":"chatgpt","branch":"chatgpt/extension-coordination-ui"}
```

The task owner or creator can update a task with `PATCH /api/coordination/tasks/{task_id}`:

```json
{"agent":"chatgpt","status":"in_review","branch":"chatgpt/extension-coordination-ui"}
```

Supported statuses are `open`, `claimed`, `in_review`, `done`, and `blocked`. The popup exposes the status control only for tasks where the selected agent is the owner or creator. Claiming and status changes are explicit button actions; nothing is claimed or updated automatically.

## File locks

The popup can list active locks, acquire one for a project-relative path, and release a lock acquired through that popup. Lock paths must not be absolute and may not contain empty, `.`, or `..` path segments. The bridge accepts TTL values from 30 seconds to 24 hours; the popup offers 15 minutes, 30 minutes, 1 hour, or 4 hours.

Acquire request:

```json
{"path":"Event sheets/Events.xml","agent":"chatgpt","task_id":"C2-XXXXXXXX","ttl_seconds":900}
```

The bridge returns a random release token. The extension stores that token in `browser.storage.local` (not synced storage) so it can submit the exact token when the user presses **Release**. Tokens are never rendered in the popup, included in messages, or copied into task descriptions. The task/lock list response contains lock metadata; the extension removes token fields before rendering it. A lock may expire or be replaced before release, in which case the bridge will reject the stale token. Locks are advisory and do not replace Git branches, review, backups, or tests.

## Messages

Messages are sent only when the user presses **Post message**. The request contains the selected agent label, the text entered in the coordination message box, and an optional task ID. Messages can be general or task-specific.

The coordination panel does not send provider conversation contents, captured replies, prompts, selected event-sheet XML, or project files to the coordination API. Existing prompt-fill, reply-capture, task claim, task update, lock, and message actions remain user-triggered.

## Manual smoke test

1. Start the bridge locally and load the unpacked extension from `browser-extension/`.
2. Open the popup. Confirm open tasks, existing statuses, messages, and active locks load.
3. Claim an open test task. Confirm the bridge records the selected agent and configured branch.
4. On a task owned by the selected agent (or created by it), change the status to `in_review`. Confirm the server records the new status and branch.
5. Acquire a lock on a disposable project-relative test path. Confirm it appears in the active lock list and the release control is available.
6. Release the test lock. Confirm it disappears from the active lock list. Also test an expired/stale token and confirm the popup reports the bridge error.
7. Post a short general message and a task-associated message. Confirm both appear in the bridge feed.
8. Close and reopen the popup. Confirm the bridge address, agent label, branch, and owned lock metadata persist.
9. Stop the bridge and refresh. Confirm the popup reports an unavailable bridge without breaking the rest of the popup.
10. Enter a non-loopback address or an unsafe lock path. Confirm the extension rejects it before sending a request.

Local browser checks must be run against the actual bridge. GitHub-side commits and unit tests do not verify local connectivity, browser permissions, CORS behavior, or popup interaction.
