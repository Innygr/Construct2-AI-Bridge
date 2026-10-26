# Browser Connector (experimental)

This extension is the no-API-key path for using an AI website in a browser tab you choose. The AI website itself handles the model session and any account or subscription requirements.

## Current workflow
1. Start the local bridge: `construct2-ai-bridge`.
2. Open a Construct 2 project in the local bridge so its summary is available.
3. In Firefox, open `about:debugging#/runtime/this-firefox`.
4. Choose **Load Temporary Add-on…** and select this folder's `manifest.json`.
5. Open the AI website you want to use in the active tab.
6. Open the extension popup and click **Fetch project summary**.
7. Click **Prepare prompt**, review the generated context, then click **Fill selected tab**.
8. Check the AI page and submit the prompt yourself.
9. To review the visible response, reopen the extension popup and click **Capture visible reply**.

## Browser compatibility
The initial target is Firefox WebExtensions (Manifest V3). Other browsers may require manifest and API adjustments.

## Limitations
- This does not use an API key and does not bypass login, subscriptions, rate limits, or site restrictions.
- Browser websites change their HTML frequently. Generic input/response detection is best-effort; some sites need a dedicated adapter.
- It does not automatically click Send, continuously monitor tabs, or apply model output to game files.
- Only use the connector on a tab you intentionally selected. The prompt is inserted only after clicking the extension button.
- The local bridge must be running at `http://127.0.0.1:8765`.
- Review any captured text. AI responses are untrusted suggestions, not executable commands.
- This experimental version requests active-tab access only when you invoke it. It does not request blanket access to all websites.
