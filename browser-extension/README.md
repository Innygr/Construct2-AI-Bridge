# Browser Connector (experimental)

Use logged-in AI websites in tabs you choose. Each site handles its own model session, login, account limits, and subscription requirements.

## Supported AI sites and browsers

The initial target AI sites are **ChatGPT**, **Claude**, and **Gemini**. The popup labels the active tab when it recognizes one of these hosts. ChatGPT and Claude now have separate site-specific connector modules for host matching, composer/reply selectors, and rich-text insertion; Gemini remains on its existing adapter. Website UI changes can still break selectors, so test each site in your browser.

- **Firefox:** supported target; load the extension temporarily from `about:debugging#/runtime/this-firefox`, choosing `manifest.json`.
- **Opera GX:** intended Chromium-based target; compatibility is not yet verified. Load the unpacked extension through the extensions manager with developer mode enabled.
- **Microsoft Edge:** intended Chromium-based target for Gemini; compatibility is not yet verified. Load the unpacked extension through `edge://extensions` with Developer mode enabled.
- **Google Chrome:** intended Chromium-based target; compatibility is not yet verified. Open `chrome://extensions`, enable Developer mode, and choose **Load unpacked**.
- **Brave:** intended Chromium-based target; compatibility is not yet verified. Open `brave://extensions`, enable Developer mode, and choose **Load unpacked**.

## Browser installation details

### Firefox

Load the extension temporarily from `about:debugging#/runtime/this-firefox`, choosing `manifest.json`.

### Opera GX

Open the extensions manager, enable developer mode, and load this folder as an unpacked extension. Opera GX is Chromium-based; compatibility is intended but not yet verified. A browser-specific manifest/build may be needed if Opera rejects Firefox-specific metadata or behaves differently.

### Microsoft Edge

Open `edge://extensions`, enable Developer mode, choose **Load unpacked**, and select the `browser-extension` folder. This is intended but not yet verified.

## Multi-AI workflow (manual, user-supervised)

1. Start the local bridge with `construct2-ai-bridge` and open a project.
2. Load the extension in any browsers you have tested successfully (Firefox is the primary target; Chromium-based browsers still need compatibility testing).
3. Open ChatGPT in one browser and Claude in the other, signed in normally.
4. Fetch the same project summary in each extension and enter the same task.
5. Choose **Parallel analysis** with different roles (for example, Architect in ChatGPT and Debugger in Claude). Prepare each prompt, fill each active tab, and submit it yourself. Both browsers can generate responses concurrently.
6. Capture each reply. Paste one AI's reply into the other AI's task field and select **Review** to cross-check it.
7. Use **Synthesis** with both proposals pasted into the task field to reconcile agreements and disagreements.
8. Compare the findings and test any approved changes in Construct 2.

## Construct 2 request inbox (no provider API key)

The extension also acts as a user-supervised relay for prompts created by the Construct 2 SDK plugin.

1. Start the local companion and load the browser extension.
2. Sign in normally to ChatGPT, Claude, or Gemini in a browser tab.
3. In Construct 2, connect the AI Bridge object and use **Send to Browser AI**. Choose a provider or **Any connected AI**.
4. Open the extension popup while the intended AI website tab is active. The queued request appears in **Construct 2 request inbox**.
5. Select **Load into active AI tab**. The extension fills the provider's visible composer; it does not press Send.
6. Review the prompt and submit it yourself on the provider website.
7. After the response is complete, open the extension popup on that same provider tab and select **Return visible AI reply to Construct 2**.
8. The local companion marks the request complete, and the Construct 2 plugin receives the response and triggers **On AI response**.

The popup polls the inbox only while open. A claimed request is associated with a locally stored browser-client ID so it can be resumed after the popup closes. The connector compares visible assistant text against the previous conversation snapshot to reduce the chance of returning an older answer.

## Agent coordination panel

The popup also provides a shared local task board, message feed, and advisory file-lock controls. It can list tasks, claim open work against a configurable Git branch, update statuses when the selected agent is the owner or creator, acquire project-relative file locks, release locks using locally stored tokens, and post explicitly entered handoff messages. The bridge address, agent label, branch, and locally held lock tokens are saved in extension-local storage (not synced storage). Lock tokens are never shown in the popup. Polling runs only while the popup is open. See [the coordination panel guide](../docs/EXTENSION_COORDINATION.md) for API contracts, safety boundaries, and a manual smoke-test checklist.

## Modes
- **Parallel analysis:** independent findings and proposals.
- **Review:** critique another assistant's proposal.
- **Synthesis:** compare proposals and identify agreements, conflicts, risks, and next steps.

## Limitations and privacy

- No API key is required for this browser workflow, but use each service's normal login and comply with its terms, limits, and controls.
- This is user-supervised collaboration, not an unattended agent system. The extension does not auto-submit prompts or run in the background; the request inbox polls only while its popup is open. Project files are never changed by the browser relay.
- Browser page layouts change. ChatGPT and Claude have dedicated adapters, but selector-based input/reply detection remains best-effort and may need updates when either website changes.
- Project context is inserted only when you click extension controls. Review it before sending it to a third-party AI service.
- The extension requests active-tab scripting when invoked. Do not use it on a tab you did not intend to share with the AI.
- The local bridge must be running at `http://127.0.0.1:8765`.
- AI output is untrusted advice. Verify all suggestions in Construct 2.
