// Shared helpers used by the Construct 2 IDE and runtime.
// Do not assume the editor's plugin-loading context exposes `window`.
(function (root) {
	"use strict";

	root.C2AIBridge = root.C2AIBridge || {};

	root.C2AIBridge.normalizeBaseURL = function (value) {
		var url = String(value || "").replace(/\s+/g, "").replace(/\/$/, "");
		// The companion service is deliberately loopback-only. Do not allow
		// the plugin to turn into a general-purpose remote HTTP client.
		if (!/^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?$/.test(url))
			return "";
		var portMatch = url.match(/:([0-9]+)$/);
		if (portMatch && (parseInt(portMatch[1], 10) < 1 || parseInt(portMatch[1], 10) > 65535))
			return "";
		return url;
	};

	root.C2AIBridge.encodeQuery = function (value) {
		return encodeURIComponent(String(value));
	};

	root.C2AIBridge.safeJSON = function (value) {
		try { return JSON.parse(value); }
		catch (e) { return null; }
	};
}(typeof globalThis !== "undefined" ? globalThis : (typeof window !== "undefined" ? window : this)));
