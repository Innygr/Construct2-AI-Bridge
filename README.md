# Construct 2 AI Bridge

A local, provider-independent bridge for inspecting Construct 2 projects and helping AI tools reason about them. It works alongside Construct 2 rather than patching the retired editor.

## Status
Phase A foundation and read-only inspection, early development. The initial build includes a local API, browser interface, CAPX ZIP inspection, and XML-based project summaries. The experimental browser connector is a no-API-key route for using an AI website in a tab you choose.

## Requirements
- Python 3.10+
- pip

## Run locally
    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e ".[dev]"
    construct2-ai-bridge

On Windows PowerShell, activate with .venv\Scripts\Activate.ps1. Then open http://127.0.0.1:8765.

## Browser-based AI (no API key)
See [browser-extension/README.md](browser-extension/README.md) for the experimental Firefox connector. It lets you fetch local project context, prepare a prompt, insert it into the AI tab you selected, and capture visible response text for review. You still use the AI website's normal login/account and must follow that site's policies. No automatic submission or project-file edits are enabled in this early connector.

## API
- GET /api/status — service status.
- POST /api/project/open — JSON body {"path": "/absolute/path/to/game.capx"}.
- GET /api/project/summary — summary for the open project.
- GET /api/objects — object types, families, and global variables.
- GET /api/events — event-sheet names and lightweight XML-derived counts.

The project path is read on the machine running the bridge. Keep this service local and only use trusted project files.

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
- Construct 2 project formats vary, so inspection is best-effort and must be verified in the editor.
- AI text is untrusted and must be reviewed before use.
- Independent community project, not affiliated with Scirra.

## License
MIT. See LICENSE.
