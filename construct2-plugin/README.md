# Construct 2 AI Bridge plugin (preview)

This is a Construct 2 SDK runtime plugin for the local Construct 2 AI Bridge companion service.

## Current scope

The plugin talks only to the loopback companion service. It supports:

- Connect / disconnect and service status checks.
- Open a local `.capx`, `.caproj`, `.c2proj`, or XML file through the companion.
- Retrieve bounded project AI context.
- Check installed local Ollama models.
- Submit a prompt to a selected local Ollama model.
- Trigger conditions and expressions for asynchronous results and errors.

ChatGPT, Claude, and Gemini are currently accessed through the separate browser-extension workflow. This plugin does not directly automate those websites or call their hosted APIs.

## Install on Construct 2 under Wine

1. Close Construct 2.
2. Copy the complete `AI_Bridge` directory into:

   `~/.wine/drive_c/Program Files/Construct 2/exporters/html5/plugins/`

3. Reopen Construct 2.
4. In the project, choose **Insert new object** and find **AI Bridge** under **Web**.
5. Insert the object once. It is a single-global object and does not need to be placed on a layout.

The folder must contain `edittime.js`, `runtime.js`, `common.js`, and `PluginIcon.ico`.

## Run the companion

Start the Python bridge on the same computer:

```bash
construct2-ai-bridge
```

The default address is `http://127.0.0.1:8765`. Keep the service bound to loopback; do not expose it to your LAN or the internet.

For browser preview, use a localhost/127.0.0.1 preview origin. The companion CORS policy permits those loopback preview origins and the supported browser-extension origins.

## Actions

- **Set base URL** — accepts only HTTP loopback URLs.
- **Connect** — checks `GET /api/status`.
- **Disconnect** — cancels pending requests and clears connection state.
- **Open project** — posts a path to `POST /api/project/open`. The path must be readable by the Python process; under Wine this means use the corresponding Linux host path, not a Wine-only `C:\\` path.
- **Get AI context** — reads `GET /api/ai-context?max_chars=...`. This only prepares context; it does not submit it to an AI.
- **Check Ollama** — reads `GET /api/ollama/status`.
- **Chat with Ollama** — posts a model, prompt, and system prompt to `POST /api/ollama/chat`.
- **Cancel requests** — aborts pending HTTP requests.

## Conditions

- On connected
- On disconnected
- On request complete (tag-filtered)
- On error (tag-filtered)
- On project opened
- On AI context ready
- On Ollama status received
- Is connected

## Expressions

- `Response`, `Error`, `RequestID`, `BaseURL`
- `ProjectContext`, `ProjectSHA256`
- `OllamaModels` (JSON array), `SelectedModel`

## Important limitations

- This is an early preview plugin. Verify it in Construct 2's editor and browser preview before relying on it in a released game.
- The plugin is intended for development projects. Do not ship a game that depends on a developer's local AI service.
- CORS is not authentication. The companion remains loopback-only and should only run on a trusted machine.
- Project opening uses paths visible to the companion process. The plugin does not yet automatically translate Wine paths.
- No project files are modified by the plugin. Project editing remains in the bridge's separate review-and-approve workflow.
