# Browser Connector (experimental)

Use logged-in AI websites in tabs you choose. Each site handles its own model session, login, account limits, and subscription requirements.

## Supported AI sites and browsers\n\nThe initial target AI sites are **ChatGPT**, **Claude**, and **Gemini**. The popup labels the active tab when it recognizes one of these hosts. Host detection is only a convenience; filling prompts and capturing replies still use best-effort generic page selectors, so each site's current interface must be tested.\n\n- **Firefox:** supported target; load the extension temporarily from `about:debugging#/runtime/this-firefox`, choosing `manifest.json`.\n- **Opera GX:** intended Chromium-based target; compatibility is not yet verified. Load the unpacked extension through the extensions manager with developer mode enabled.\n- **Microsoft Edge:** intended Chromium-based target for Gemini; compatibility is not yet verified. Load the unpacked extension through `edge://extensions` with Developer mode enabled.\n\n## Browser installation details\n\n### Firefox\n\nLoad the extension temporarily from `about:debugging#/runtime/this-firefox`, choosing `manifest.json`.\n\n### Opera GX\n\nOpen the extensions manager, enable developer mode, and load this folder as an unpacked extension. Opera GX is Chromium-based; compatibility is intended but not yet verified. A browser-specific manifest/build may be needed if Opera rejects Firefox-specific metadata or behaves differently.\n\n### Microsoft Edge\n\nOpen `edge://extensions`, enable Developer mode, choose **Load unpacked**, and select the `browser-extension` folder. This is intended but not yet verified.\n\n<!-- old browser section replaced below -->\n\n## Firefox and Opera GX

- **Firefox:** load the extension temporarily from `about:debugging#/runtime/this-firefox`, choosing `manifest.json`.
- **Opera GX:** open the extensions manager, enable developer mode, and load this folder as an unpacked extension. Opera GX is Chromium-based; compatibility is intended but not yet verified. A browser-specific manifest/build may be needed if Opera rejects Firefox-specific metadata or behaves differently.

## Multi-AI workflow (manual, user-supervised)

1. Start the local bridge with `construct2-ai-bridge` and open a project.
2. Load the extension in Firefox and Opera GX.
3. Open ChatGPT in one browser and Claude in the other, signed in normally.
4. Fetch the same project summary in each extension and enter the same task.
5. Choose **Parallel analysis** with different roles (for example, Architect in ChatGPT and Debugger in Claude). Prepare each prompt, fill each active tab, and submit it yourself. Both browsers can generate responses concurrently.
6. Capture each reply. Paste one AI's reply into the other AI's task field and select **Review** to cross-check it.
7. Use **Synthesis** with both proposals pasted into the task field to reconcile agreements and disagreements.
8. Compare the findings and test any approved changes in Construct 2.

## Modes
- **Parallel analysis:** independent findings and proposals.
- **Review:** critique another assistant's proposal.
- **Synthesis:** compare proposals and identify agreements, conflicts, risks, and next steps.

## Limitations and privacy

- No API key is required for this browser workflow, but use each service's normal login and comply with its terms, limits, and controls.
- This is coordinated manual collaboration, not an unattended multi-agent system. It does not auto-submit prompts, continuously monitor tabs, or modify project files.
- Browser page layouts change. Generic input/response detection is best-effort and may need site-specific adapters.
- Project context is inserted only when you click extension controls. Review it before sending it to a third-party AI service.
- The extension requests active-tab scripting when invoked. Do not use it on a tab you did not intend to share with the AI.
- The local bridge must be running at `http://127.0.0.1:8765`.
- AI output is untrusted advice. Verify all suggestions in Construct 2.
