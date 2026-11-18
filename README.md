# Construct 2 AI Bridge

A local, provider-independent bridge for inspecting Construct 2 projects and helping AI tools reason about them. It works alongside Construct 2 rather than patching the retired editor.

## Status
Phase A foundation with read/write XML project integration, early development. Includes a local API, browser interface, CAPX ZIP inspection with bounded XML reads, reviewed XML editing with automatic backups and atomic writes, XML-based project summaries and detection diagnostics, and an experimental browser extension for user-supervised AI workflows. A GitHub Actions workflow runs the Python test suite on pushes and pull requests, including API endpoint regression tests.

## Requirements
- Python 3.10+
- pip

## Run locally
    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e ".[dev]"
    construct2-ai-bridge

To launch the interface in a separate browser window once the local service is ready, run `construct2-ai-bridge --window`. You can also set a custom local port with `--port 8766`; the interface stays bound to loopback only.

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`. Then open http://127.0.0.1:8765.

## Browser-based AI without API keys
See [browser-extension/README.md](browser-extension/README.md). The extension targets ChatGPT, Claude, and Gemini, with planned desktop-browser coverage for Firefox, Opera GX, Microsoft Edge, Google Chrome, and Brave. Firefox is the primary target; Chromium-browser compatibility is intended but must be verified in each browser. Use ChatGPT and Claude in their normal logged-in tabs. Multi-AI modes include independent parallel analysis, cross-review, and synthesis. The browser extension remains user-supervised for hosted AI providers: it prepares prompts and captures visible replies. Project edits are reviewed and applied through the local bridge editor.

## MCP integration for ChatGPT and local clients

The MCP adapter adds local stdio support plus a separately authenticated Streamable HTTP endpoint for an HTTPS tunnel. It exposes project summaries, objects, event sheets, selected XML, AI context, and a proposal-first XML patch workflow. Writes still use the existing validation, stale-project check, backup, and atomic replacement path.

See **[MCP integration and tunnel setup](docs/MCP-INTEGRATION.md)** for installation, local client configuration, Cloudflare Tunnel setup, and the ChatGPT web connector details. The remote ChatGPT endpoint requires a user-configured HTTPS tunnel hostname and bearer token; neither is embedded in the repository.

## Read/write workflow

Open a `.capx` or `.caproj`, select an XML document in the **XML editor · read & write** panel, and load its full contents. Edit it directly or ask Ollama for a complete updated XML proposal, then use **Use response as XML draft**. Review the changed-line preview and click **Apply approved changes to project**. The bridge validates the XML and project archive, checks that the on-disk project has not changed since it was loaded, saves a numbered backup, and atomically replaces the file. Reload the project in Construct 2 to verify runtime behavior. The editor also offers an experimental structural-patch mode: it exposes a bounded XML node tree with child-index paths, asks Ollama for minimal JSON operations, and applies reviewed operations through the same backup/validation/write path. Supported operations are setting/removing attributes, setting text, appending an XML fragment, and deleting a non-root node. This remains schema-agnostic—not a semantic Construct 2 event editor—and ElementTree may normalize XML formatting or namespace prefixes. Preserve unknown project structures and review generated changes carefully.

## Local AI with Ollama

Install Ollama separately and pull at least one model (for example, `ollama pull qwen2.5:7b`). Start Ollama, run the bridge, and open the local interface. The Ollama panel checks `http://127.0.0.1:11434`, lists installed models, and lets you submit prepared debugging context plus the currently loaded full XML document to a selected model.

- Ollama is optional; project inspection and browser-based AI workflows work without it.
- The bridge contacts only the local Ollama address at `127.0.0.1:11434`; there is no configurable remote host.
- Model requests are user-triggered and non-streaming. Large prompts and slower models can take several minutes.
- Pulling/downloading models is handled by the Ollama application, not by this bridge.
- No prompt is sent to Ollama until you click **Run with Ollama**. Review project context before submitting it.
- API endpoints: `GET /api/ollama/status` and `POST /api/ollama/chat`.

## API
- GET /api/status — service status (reports read/write-with-approval mode).
- POST /api/project/open — JSON body `{"path": "/absolute/path/to/game.capx"}`.
- GET /api/project/summary — summary for the open project, including bounded per-XML event outlines with stable-in-that-document `event_id` / `event_index` references, nesting depth, condition/action labels, and basic parameter attributes where detectable. The outline parser recognizes normalized `event-block` nodes as well as generic event/group nodes and reports when the outline reaches its safety limit.
- GET /api/project/tree?document=events.xml — returns a bounded XML node tree (up to 1,000 nodes and 64 levels) with child-index paths for structural patch proposals.
- POST /api/project/patch — applies 1–100 reviewed path-based XML operations (`set_attribute`, `remove_attribute`, `set_text`, `append_xml`, `delete_node`) using the same stale-hash check, backup, validation, and atomic replacement as normal writes. The root cannot be deleted.
- POST /api/project/write — applies one explicitly approved XML document update. Requires `document`, full `xml`, and the `expected_project_sha256` returned by `/api/project/open`; validates XML, rejects stale project hashes, creates a numbered `.bak` backup, validates the replacement archive/file, and atomically replaces the project.
- GET /api/project/xml?documents=events.xml — returns the complete XML text for explicitly selected XML document names from the currently open project. Repeat the `documents` query parameter for multiple sheets. This endpoint does not truncate XML; the browser extension uses it only for checked event sheets.
- GET /api/objects — object types, families, and global variables.
- GET /api/events — event-sheet names, lightweight XML-derived counts, and bounded event outlines with `event_id` / `event_index` references and condition/action parameter details where detectable. Outlines are heuristic and may not map every Construct 2 version's event format.
- GET /api/ai-context — returns a bounded JSON context string designed to paste into an AI chat. Optional repeated `event_ids` parameters focus the context on selected events; `max_chars` accepts 1,000–40,000 characters. Unknown event IDs return HTTP 400. Nothing is sent to an AI provider automatically.

Keep the service local and only use trusted project files.

## Roadmap
1. A0 — local service, UI, project loading.
2. A1 — improve project parsing against real projects.
3. A2 — provider-independent adapters for hosted and local AI, plus browser-based AI workflow.
4. A3 — event-sheet explanation and change proposals.
5. A4 — safe editing with previews, validation, backups, and explicit approval.
6. A5 — MCP adapter for compatible AI clients.
7. A6 — tests and documentation using sanitized sample projects.
8. B0 — one-command companion window launch (`construct2-ai-bridge --window`).
9. B1 — build and validate a Construct 2 SDK plugin that can launch the companion; do not rely on undocumented editor DOM hooks for a docked panel.

## Safety and limitations
- Project writes are limited to explicitly approved XML documents. Each write validates the XML, checks a project hash to reject stale edits, creates a numbered backup, validates a temporary replacement, and uses atomic replacement. The bridge does not execute project content.
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

Construct 2 is officially retired, but its JavaScript SDK supports third-party plugins with editor-time and runtime components. A plugin can add event-system actions/conditions/expressions, but that SDK does not itself provide a supported dockable ChatGPT-style editor panel. The companion window is the first practical integration step; a plugin bridge will be evaluated separately.

The AI context endpoint includes explicit instructions to ground advice in supplied evidence, cite event IDs, acknowledge uncertainty, and propose rather than perform edits. It truncates event details to respect the requested character budget and marks the result as truncated. The browser UI lets you describe a bug, select relevant events, and prepare a combined debugging prompt for manual review and copying; the bug description is clearly labeled as user-provided, and the combined prompt is kept within a 12,000-character budget.
