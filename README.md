# Construct 2 AI Bridge

A local, provider-independent bridge for inspecting Construct 2 projects and helping AI tools reason about them. It works alongside Construct 2 rather than patching the retired editor.

## Status
Phase A foundation and read-only inspection, early development. Includes a local API, browser interface, CAPX ZIP inspection with bounded XML reads, XML-based project summaries and detection diagnostics, and an experimental browser extension for user-supervised AI workflows. A GitHub Actions workflow runs the Python test suite on pushes and pull requests, including API endpoint regression tests.

## Requirements
- Python 3.10+
- pip

## Run locally
    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e ".[dev]"
    construct2-ai-bridge

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`. Then open http://127.0.0.1:8765.

## Browser-based AI without API keys
See [browser-extension/README.md](browser-extension/README.md). The extension targets ChatGPT, Claude, and Gemini, with planned desktop-browser coverage for Firefox, Opera GX, Microsoft Edge, Google Chrome, and Brave. Firefox is the primary target; Chromium-browser compatibility is intended but must be verified in each browser. Use ChatGPT and Claude in their normal logged-in tabs. Multi-AI modes include independent parallel analysis, cross-review, and synthesis. This first implementation is manual and user-supervised: it prepares prompts and captures visible replies but does not auto-submit or edit project files.

## API
- GET /api/status — service status.
- POST /api/project/open — JSON body `{"path": "/absolute/path/to/game.capx"}`.
- GET /api/project/summary — summary for the open project, including bounded per-XML event outlines with stable-in-that-document `event_id` / `event_index` references, nesting depth, condition/action labels, and basic parameter attributes where detectable. The outline parser recognizes normalized `event-block` nodes as well as generic event/group nodes and reports when the outline reaches its safety limit.
- GET /api/objects — object types, families, and global variables.
- GET /api/events — event-sheet names, lightweight XML-derived counts, and bounded event outlines with `event_id` / `event_index` references and condition/action parameter details where detectable. Outlines are heuristic and may not map every Construct 2 version's event format.\n- GET /api/ai-context — returns a bounded JSON context string designed to paste into an AI chat. Optional repeated `event_ids` parameters focus the context on selected events; `max_chars` accepts 1,000–40,000 characters. Unknown event IDs return HTTP 400. Nothing is sent to an AI provider automatically.

Keep the service local and only use trusted project files.

## Roadmap
1. A0 — local service, UI, project loading.
2. A1 — improve project parsing against real projects.
3. A2 — provider-independent adapters for hosted and local AI, plus browser-based AI workflow.
4. A3 — event-sheet explanation and change proposals.
5. A4 — safe editing with previews, validation, backups, and explicit approval.
6. A5 — MCP adapter for compatible AI clients.
7. A6 — tests and documentation using sanitized sample projects.
8. Phase B, only after A — investigate companion/editor integration and live interaction where technically feasible.

## Safety and limitations
- This version does not modify project files or execute project content.
- XML DTD/entity declarations are rejected.
- The server binds to loopback only; do not expose it to a network.
- Construct 2 project formats vary, so inspection is best-effort. Diagnostics indicate structures the parser did not detect; they are not proof that the project is broken. Verify results in the editor.
- AI text is untrusted and must be reviewed before use.
- Independent community project, not affiliated with Scirra.

## License
MIT. See LICENSE


Event outlines preserve explicit event disabled/enabled flags when the project XML provides recognizable boolean attributes. Missing or unknown values are not guessed.

Condition/action details retain short inline text when present, alongside attribute-based parameters.

CAPX inspection reports when XML archive entries were skipped because of unsafe paths, malformed content, per-file size limits, or the aggregate XML size limit. A partial summary can still be returned when at least one XML document is readable; check `diagnostics` before treating the summary as complete.

Each event outline includes a deterministic `event_id` formed from its XML document name and one-based outline order (for example, `events.xml::event:0001`), plus the numeric `event_index`. These identifiers help AI responses refer to the same event within a given inspected file version; they are not persistent IDs across edits that reorder or insert events.

The AI context endpoint includes explicit instructions to ground advice in supplied evidence, cite event IDs, acknowledge uncertainty, and propose rather than perform edits. It truncates event details to respect the requested character budget and marks the result as truncated. The browser UI lets you describe a bug, select relevant events, and prepare a combined debugging prompt for manual review and copying; the bug description is clearly labeled as user-provided, and the combined prompt is kept within a 12,000-character budget.
