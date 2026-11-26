# Construct 2 AI Bridge plugin (preview)

A Construct 2 SDK runtime plugin for the local Construct 2 AI Bridge companion service.

## Capabilities

The plugin is a development-time client for the local companion. It supports:

- Connect / disconnect and service status checks.
- Open a local `.capx`, `.caproj`, `.c2proj`, or XML project through the companion.
- Retrieve bounded project AI context.
- Check installed local Ollama models and submit prompts to Ollama.
- Queue prompts for ChatGPT, Claude, or Gemini through the browser connector, without a provider API key.
- Wait for a browser response and expose it through Construct 2 triggers and expressions.

The browser relay uses the normal signed-in provider website session. It does not bypass subscriptions, usage limits, logins, or provider controls.

## Install on Construct 2 under Wine

1. Close Construct 2.
2. Copy the complete `AI_Bridge` directory into:

   `~/.wine/drive_c/Program Files/Construct 2/exporters/html5/plugins/`

3. Reopen Construct 2.
4. In the project, choose **Insert new object** and find **AI Bridge** under **Web**.
5. Insert the object once. It is a single-global object and does not need to be placed on a layout.

The folder must contain `edittime.js`, `runtime.js`, `common.js`, and `PluginIcon.ico`.

## Run the companion and browser connector

Start the companion on the same computer:

```bash
construct2-ai-bridge
```

The default address is `http://127.0.0.1:8765`. Keep it bound to loopback; do not expose it to a LAN or the internet.

Load the `browser-extension` folder as a temporary/unpacked extension (see [the browser connector guide](../browser-extension/README.md)). Sign in normally to ChatGPT, Claude, or Gemini. Keep the extension popup open while checking the Construct 2 request inbox.

For browser preview, use a localhost/127.0.0.1 preview origin. The companion CORS policy permits those loopback preview origins and supported browser-extension origins.

## Browser AI workflow (no API key)

1. Start the companion and load the browser extension.
2. Open a supported AI website in a tab and sign in normally.
3. In Construct 2, use **AI Bridge → Connect**.
4. Use **AI Bridge → Send to Browser AI** and choose Any, ChatGPT, Claude, or Gemini. Optionally include project context previously retrieved with **Get AI Context**.
5. Open the extension popup while the intended AI website tab is active. The request appears in **Construct 2 request inbox**.
6. Click **Load into active AI tab**. The extension fills the prompt composer but does not submit it.
7. Review the prompt and press **Send** on the AI website yourself. Wait for the answer to finish.
8. Reopen the extension popup on that AI tab and click **Return visible AI reply to Construct 2**.
9. The plugin receives the result and triggers **On AI response**. Read the answer with the `AIResponse` or `Response` expression.

The extension stores a browser-client identifier locally so the same popup instance can resume a claimed request after it is closed. It checks that the visible assistant text differs from the reply present before the prompt was loaded.

## Actions

- **Set base URL** — accepts only HTTP loopback URLs.
- **Connect / Disconnect** — checks the companion and cancels pending work on disconnect.
- **Open project** — sends a path to `POST /api/project/open`. The path must be readable by the Python process; under Wine use the corresponding Linux host path, not a Wine-only `C:\\` path.
- **Get AI context** — retrieves bounded project context. It does not submit it anywhere by itself.
- **Check Ollama / Chat with Ollama** — interacts with a local Ollama service.
- **Send to Browser AI** — creates a tagged request for the selected browser provider and waits for its response. The extension must be installed and used on the same computer.
- **Cancel requests** — aborts HTTP requests and marks pending browser relay requests cancelled.

## Conditions

- On connected / disconnected
- On request complete (tag-filtered)
- On error (tag-filtered)
- On project opened
- On context ready
- On Ollama status
- On AI response (tag-filtered)
- Is connected

## Expressions

- `Response`, `AIResponse`, `Error`, `RequestID`, `RequestTag`, `BaseURL`
- `ProjectContext`, `ProjectSHA256`
- `OllamaModels` (JSON array), `SelectedModel` (for browser requests this is `browser:<provider>`)

## Important limitations

- This is an early preview plugin. It has passed automated syntax and backend tests, but must still be tested inside the actual Construct 2 editor and preview browser.
- The browser popup checks for work while it is open. The user must manually submit the prompt on the AI website and explicitly return the visible reply.
- Hosted ChatGPT/Claude/Gemini responses use the website UI; there is no API key or direct hosted API integration.
- The plugin and companion are for local development workflows, not shipped game functionality.
- CORS is not authentication. The companion remains loopback-only and should only run on a trusted computer.
- Project opening uses paths visible to the companion process. The plugin does not yet automatically translate Wine paths.
- No project files are modified by the browser AI relay. Project editing remains in the bridge's separate review-and-approve workflow.
