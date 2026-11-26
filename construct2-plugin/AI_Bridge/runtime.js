// ECMAScript 5 runtime for Construct 2.
"use strict";

assert2(cr, "cr namespace not created");
assert2(cr.plugins_, "cr.plugins_ not created");

cr.plugins_.AIBridge = function(runtime)
{
	this.runtime = runtime;
};

(function ()
{
	var pluginProto = cr.plugins_.AIBridge.prototype;

	pluginProto.Type = function(plugin)
	{
		this.plugin = plugin;
		this.runtime = plugin.runtime;
	};
	var typeProto = pluginProto.Type.prototype;
	typeProto.onCreate = function() {};

	pluginProto.Instance = function(type)
	{
		this.type = type;
		this.runtime = type.runtime;
		this.baseURL = "http://127.0.0.1:8765";
		this.connected = false;
		this.lastResponse = "";
		this.lastError = "";
		this.lastRequestID = "";
		this.lastTag = "";
		this.projectContext = "";
		this.projectSHA256 = "";
		this.ollamaModels = "[]";
		this.selectedModel = "";
		this._nextRequestID = 1;
		this._requests = [];
		this._browserAIRequests = {};
	};

	var instanceProto = pluginProto.Instance.prototype;

	instanceProto.onCreate = function()
	{
		if (this.properties && this.properties.length)
			this.baseURL = this._normalizeBaseURL(this.properties[0]) || this.baseURL;
	};

	instanceProto.onDestroy = function()
	{
		this.cancelRequests(false);
		this.cancelBrowserAIRequests();
	};

	instanceProto.saveToJSON = function()
	{
		return {
			"baseURL": this.baseURL,
			"lastResponse": this.lastResponse,
			"projectContext": this.projectContext,
			"projectSHA256": this.projectSHA256
		};
	};

	instanceProto.loadFromJSON = function(o)
	{
		this.baseURL = this._normalizeBaseURL(o["baseURL"]) || "http://127.0.0.1:8765";
		this.lastResponse = o["lastResponse"] || "";
		this.projectContext = o["projectContext"] || "";
		this.projectSHA256 = o["projectSHA256"] || "";
		this.connected = false;
		this.lastError = "";
		this.lastRequestID = "";
		this.ollamaModels = "[]";
		this.selectedModel = "";
		this._browserAIRequests = {};
	};

	instanceProto._normalizeBaseURL = function(value)
	{
		if (window.C2AIBridge && window.C2AIBridge.normalizeBaseURL)
			return window.C2AIBridge.normalizeBaseURL(value);
		var url = String(value || "").replace(/\s+/g, "").replace(/\/$/, "");
		return /^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?$/.test(url) ? url : "";
	};

	instanceProto._trigger = function(condition)
	{
		this.runtime.trigger(condition, this);
	};

	instanceProto._removeRequest = function(xhr)
	{
		for (var i = this._requests.length - 1; i >= 0; --i)
			if (this._requests[i] === xhr)
				this._requests.splice(i, 1);
	};

	instanceProto._request = function(method, path, body, tag, callback, timeout)
	{
		var self = this;
		var xhr = new XMLHttpRequest();
		var requestID = "c2ai-" + (this._nextRequestID++);
		var completed = false;
		this.lastRequestID = requestID;
		this.lastTag = String(tag || "");
		this.lastError = "";
		this._requests.push(xhr);

		function finishError(message)
		{
			if (completed) return;
			completed = true;
			self._removeRequest(xhr);
			self.lastError = String(message || "Request failed.");
			self.lastTag = String(tag || "");
			self._trigger(pluginProto.cnds.OnError);
		}
		function finishSuccess(data, raw)
		{
			if (completed) return;
			completed = true;
			self._removeRequest(xhr);
			self.lastResponse = raw || "";
			self.lastTag = String(tag || "");
			self.lastError = "";
			if (callback) callback(data);
			self._trigger(pluginProto.cnds.OnRequestComplete);
		}

		try
		{
			xhr.open(method, this.baseURL + path, true);
			xhr.timeout = timeout || 30000;
			xhr.setRequestHeader("Accept", "application/json");
			if (body !== null && typeof body !== "undefined")
				xhr.setRequestHeader("Content-Type", "application/json");
			xhr.onreadystatechange = function()
			{
				if (xhr.readyState !== 4 || completed || xhr._c2aiSilentAbort) return;
				var raw = xhr.responseText || "";
				var data = window.C2AIBridge ? window.C2AIBridge.safeJSON(raw) : null;
				if (xhr.status >= 200 && xhr.status < 300)
				{
					if (data === null)
						finishError("The bridge returned an invalid JSON response.");
					else
						finishSuccess(data, raw);
				}
				else
				{
					var detail = data && data.detail ? data.detail : ("HTTP " + xhr.status);
					if (typeof detail !== "string") detail = JSON.stringify(detail);
					finishError(detail);
				}
			};
			xhr.onerror = function() { finishError("Could not reach the local bridge. Check that it is running and that Construct 2 preview uses localhost or 127.0.0.1."); };
			xhr.ontimeout = function() { finishError("The request timed out."); };
			xhr.onabort = function() { if (xhr._c2aiSilentAbort) completed = true; else finishError("The request was cancelled."); };
			if (body !== null && typeof body !== "undefined")
				xhr.send(JSON.stringify(body));
			else
				xhr.send();
		}
		catch (e)
		{
			finishError(e && e.message ? e.message : String(e));
		}
		return requestID;
	};

	instanceProto.cancelRequests = function(raiseEvents)
	{
		var pending = this._requests.slice(0);
		this._requests = [];
		for (var i = 0; i < pending.length; i++)
		{
			pending[i]._c2aiSilentAbort = true;
			try { pending[i].abort(); } catch (e) {}
		}
		if (raiseEvents && pending.length)
		{
			this.lastError = "Pending requests were cancelled.";
			this._trigger(pluginProto.cnds.OnError);
		}
	};


	instanceProto._pollBrowserAIRequest = function(requestID, tag, startedAt)
	{
		var self = this;
		var xhr = new XMLHttpRequest();
		var retryQueued = false;
		function scheduleRetry()
		{
			if (retryQueued || !self._browserAIRequests[requestID]) return;
			retryQueued = true;
			if (Date.now() - startedAt > 600000)
			{
				delete self._browserAIRequests[requestID];
				self.lastRequestID = requestID;
				self.lastTag = tag;
				self.lastError = "Timed out waiting for the browser AI reply. Check the browser connector and try again.";
				try
				{
					var cancelXHR = new XMLHttpRequest();
					cancelXHR.open("POST", self.baseURL + "/api/ai/requests/" + encodeURIComponent(requestID) + "/cancel", true);
					cancelXHR.send();
				}
				catch (cancelError) {}
				self._trigger(pluginProto.cnds.OnError);
				return;
			}
			self._browserAIRequests[requestID].timer = window.setTimeout(function()
			{
				self._pollBrowserAIRequest(requestID, tag, startedAt);
			}, 1800);
		}
		try
		{
			xhr.open("GET", this.baseURL + "/api/ai/requests/" + encodeURIComponent(requestID), true);
			xhr.timeout = 12000;
			xhr.setRequestHeader("Accept", "application/json");
			xhr.onreadystatechange = function()
			{
				if (xhr.readyState !== 4 || !self._browserAIRequests[requestID]) return;
				if (xhr.status < 200 || xhr.status >= 300)
				{
					scheduleRetry();
					return;
				}
				var data = window.C2AIBridge ? window.C2AIBridge.safeJSON(xhr.responseText || "") : null;
				var item = data && data.request;
				if (!item)
				{
					scheduleRetry();
					return;
				}
				if (item.status === "pending" || item.status === "claimed")
				{
					scheduleRetry();
					return;
				}
				delete self._browserAIRequests[requestID];
				self.lastRequestID = requestID;
				self.lastTag = tag;
				if (item.status === "completed")
				{
					self.lastResponse = item.response || "";
					self.lastError = "";
					self.selectedModel = "browser:" + (item.claimed_provider || item.provider || "unknown");
					self._trigger(pluginProto.cnds.OnAIResponse);
					self._trigger(pluginProto.cnds.OnRequestComplete);
				}
				else
				{
					self.lastError = item.error || ("Browser AI request ended with status: " + item.status);
					self._trigger(pluginProto.cnds.OnError);
				}
			};
			xhr.onerror = scheduleRetry;
			xhr.ontimeout = scheduleRetry;
			xhr.send();
		}
		catch (e)
		{
			scheduleRetry();
		}
	};

	instanceProto.cancelBrowserAIRequests = function()
	{
		var ids = [];
		var id;
		for (id in this._browserAIRequests)
		{
			if (this._browserAIRequests.hasOwnProperty(id))
			{
				ids.push(id);
				if (this._browserAIRequests[id].timer)
					window.clearTimeout(this._browserAIRequests[id].timer);
				}
			}
		this._browserAIRequests = {};
		for (var i = 0; i < ids.length; i++)
		{
			try
			{
				var xhr = new XMLHttpRequest();
				xhr.open("POST", this.baseURL + "/api/ai/requests/" + encodeURIComponent(ids[i]) + "/cancel", true);
				xhr.send();
			}
			catch (e) {}
		}
	};

	instanceProto.getDebuggerValues = function(propsections)
	{
		propsections.push({
			"title": "AI Bridge",
			"properties": [
				{"name": "Connected", "value": this.connected, "readonly": true},
				{"name": "Base URL", "value": this.baseURL, "readonly": true},
				{"name": "Last request ID", "value": this.lastRequestID, "readonly": true},
				{"name": "Last error", "value": this.lastError, "readonly": true}
			]
		});
	};

	function Cnds() {}
	Cnds.prototype.OnConnected = function() { return true; };
	Cnds.prototype.OnDisconnected = function() { return true; };
	Cnds.prototype.OnRequestComplete = function(tag) { return cr.equals_nocase(tag, this.lastTag); };
	Cnds.prototype.OnError = function(tag) { return cr.equals_nocase(tag, this.lastTag); };
	Cnds.prototype.OnProjectOpened = function() { return true; };
	Cnds.prototype.OnContextReady = function() { return true; };
	Cnds.prototype.OnOllamaStatus = function() { return true; };
	Cnds.prototype.OnAIResponse = function(tag) { return cr.equals_nocase(tag, this.lastTag); };
	Cnds.prototype.IsConnected = function() { return this.connected; };
	pluginProto.cnds = new Cnds();

	function Acts() {}
	Acts.prototype.SetBaseURL = function(url)
	{
		var normalized = this._normalizeBaseURL(url);
		if (!normalized)
		{
			this.lastError = "Only loopback URLs are permitted (localhost, 127.0.0.1 or ::1).";
			this.lastTag = "set-base-url";
			this._trigger(pluginProto.cnds.OnError);
			return;
		}
		this.baseURL = normalized;
		this.connected = false;
	};
	Acts.prototype.Connect = function()
	{
		var self = this;
		this._request("GET", "/api/status", null, "connect", function(data)
		{
			self.connected = data.status === "ok";
			if (self.connected) self._trigger(pluginProto.cnds.OnConnected);
			else {
				self.lastError = "The service responded, but did not identify as Construct 2 AI Bridge.";
				self._trigger(pluginProto.cnds.OnError);
			}
		});
	};
	Acts.prototype.Disconnect = function()
	{
		this.cancelRequests(false);
		this.connected = false;
		this._trigger(pluginProto.cnds.OnDisconnected);
	};
	Acts.prototype.OpenProject = function(tag, path)
	{
		var self = this;
		this._request("POST", "/api/project/open", {"path": String(path)}, tag, function(data)
		{
			self.projectSHA256 = data.project_sha256 || "";
			self._trigger(pluginProto.cnds.OnProjectOpened);
		});
	};
	Acts.prototype.GetAIContext = function(tag, maxChars)
	{
		var self = this;
		var limit = Math.max(1000, Math.min(40000, Math.floor(maxChars || 12000)));
		this._request("GET", "/api/ai-context?max_chars=" + encodeURIComponent(limit), null, tag, function(data)
		{
			self.projectContext = data.context || "";
			self._trigger(pluginProto.cnds.OnContextReady);
		});
	};
	Acts.prototype.CheckOllama = function(tag)
	{
		var self = this;
		this._request("GET", "/api/ollama/status", null, tag, function(data)
		{
			self.ollamaModels = JSON.stringify(data.models || []);
			self._trigger(pluginProto.cnds.OnOllamaStatus);
		});
	};
	Acts.prototype.ChatWithOllama = function(tag, model, prompt, system)
	{
		var self = this;
		if (!model || !prompt)
		{
			this.lastError = "A model and prompt are required.";
			this.lastTag = String(tag || "");
			this._trigger(pluginProto.cnds.OnError);
			return;
		}
		this.selectedModel = String(model);
		this._request("POST", "/api/ollama/chat", {
			"model": String(model),
			"prompt": String(prompt),
			"system": String(system || "")
		}, tag, function(data)
		{
			self.lastResponse = data.response || "";
			self.selectedModel = data.model || self.selectedModel;
		}, 300000);
	};
	Acts.prototype.SendToBrowserAI = function(tag, providerIndex, prompt, system, includeContext)
	{
		var self = this;
		var providers = ["any", "chatgpt", "claude", "gemini"];
		var provider = providers[providerIndex] || "any";
		var message = String(prompt || "");
		if (includeContext && this.projectContext)
			message += "\n\nPROJECT CONTEXT (from the local Construct 2 AI Bridge):\n" + this.projectContext;
		if (!message)
		{
			this.lastTag = String(tag || "");
			this.lastError = "A prompt is required.";
			this._trigger(pluginProto.cnds.OnError);
			return;
		}
		this._request("POST", "/api/ai/requests", {
			"provider": provider,
			"prompt": message,
			"system": String(system || "")
		}, tag, function(data)
		{
			var requestID = data.request && data.request.id;
			if (!requestID)
			{
				self.lastError = "The bridge did not return an AI request ID.";
				self._trigger(pluginProto.cnds.OnError);
				return;
			}
			self.lastRequestID = requestID;
			self.lastTag = String(tag || "");
			self._browserAIRequests[requestID] = {"tag": String(tag || ""), "timer": null};
			self._pollBrowserAIRequest(requestID, String(tag || ""), Date.now());
		}, 30000);
	};
	Acts.prototype.CancelRequests = function()
	{
		this.cancelRequests(true);
		this.cancelBrowserAIRequests();
	};
	pluginProto.acts = new Acts();

	function Exps() {}
	Exps.prototype.Response = function(ret) { ret.set_string(this.lastResponse); };
	Exps.prototype.Error = function(ret) { ret.set_string(this.lastError); };
	Exps.prototype.RequestID = function(ret) { ret.set_string(this.lastRequestID); };
	Exps.prototype.BaseURL = function(ret) { ret.set_string(this.baseURL); };
	Exps.prototype.ProjectContext = function(ret) { ret.set_string(this.projectContext); };
	Exps.prototype.OllamaModels = function(ret) { ret.set_string(this.ollamaModels); };
	Exps.prototype.ProjectSHA256 = function(ret) { ret.set_string(this.projectSHA256); };
	Exps.prototype.SelectedModel = function(ret) { ret.set_string(this.selectedModel); };
	Exps.prototype.RequestTag = function(ret) { ret.set_string(this.lastTag); };
	pluginProto.exps = new Exps();
}());
