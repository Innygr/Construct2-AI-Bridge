function GetPluginSettings()
{
	return {
		"name": "AI Bridge",
		"id": "AIBridge",
		"version": "0.1",
		"description": "Connect Construct 2 to the local Construct 2 AI Bridge companion service.",
		"author": "Innygr",
		"help url": "https://github.com/Innygr/Construct2-AI-Bridge",
		"category": "Web",
		"type": "object",
		"rotatable": false,
		"flags": pf_singleglobal
	};
}

// Conditions
AddCondition(0, cf_trigger, "On connected", "Connection", "On connected", "Triggered after the local bridge responds successfully.", "OnConnected");
AddCondition(1, cf_trigger, "On disconnected", "Connection", "On disconnected", "Triggered when the plugin disconnects.", "OnDisconnected");
AddStringParam("Tag", "Request tag used to identify this operation.", '""');
AddCondition(2, cf_trigger, "On request complete", "Requests", "On request <b>{0}</b> complete", "Triggered when a tagged request completes successfully.", "OnRequestComplete");
AddStringParam("Tag", "Request tag used to identify this operation.", '""');
AddCondition(3, cf_trigger, "On error", "Requests", "On request <b>{0}</b> error", "Triggered when a tagged request fails.", "OnError");
AddCondition(4, cf_trigger, "On project opened", "Project", "On project opened", "Triggered after a project is loaded by the bridge.", "OnProjectOpened");
AddCondition(5, cf_trigger, "On context ready", "Project", "On AI context ready", "Triggered after project context has been retrieved.", "OnContextReady");
AddCondition(6, cf_trigger, "On Ollama status", "Ollama", "On Ollama status received", "Triggered after the local Ollama status has been checked.", "OnOllamaStatus");
AddCondition(7, cf_none, "Is connected", "Connection", "Is connected", "True when the local bridge has responded successfully.", "IsConnected");
AddStringParam("Tag", "Tag used when the browser AI request was created.", '""');
AddCondition(8, cf_trigger, "On AI response", "Browser AI", "On browser AI response <b>{0}</b>", "Triggered when the browser connector returns the tagged AI response.", "OnAIResponse");

// Actions
AddStringParam("Base URL", "Loopback URL of the local bridge. Only localhost, 127.0.0.1 and ::1 are accepted.", '"http://127.0.0.1:8765"');
AddAction(0, 0, "Set base URL", "Connection", "Set base URL to <b>{0}</b>", "Set the loopback address of the local companion service.", "SetBaseURL");
AddAction(1, 0, "Connect", "Connection", "Connect to local bridge", "Check whether the local companion service is available.", "Connect");
AddAction(2, 0, "Disconnect", "Connection", "Disconnect", "Mark the plugin disconnected and cancel pending requests.", "Disconnect");
AddStringParam("Tag", "A tag used by the completion and error triggers.", '"open-project"');
AddStringParam("Project path", "Absolute path to a .capx, .caproj, .c2proj or XML project file as visible to the Python bridge process.", '""');
AddAction(3, 0, "Open project", "Project", "Open project <b>{1}</b> (tag <i>{0}</i>)", "Ask the local bridge to inspect a Construct 2 project file.", "OpenProject");
AddStringParam("Tag", "A tag used by the completion and error triggers.", '"ai-context"');
AddNumberParam("Maximum characters", "Maximum context length (1000 to 40000).", "12000");
AddAction(4, 0, "Get AI context", "Project", "Get AI context (max <b>{1}</b> chars, tag <i>{0}</i>)", "Retrieve bounded project context. This does not send it to an AI provider.", "GetAIContext");
AddStringParam("Tag", "A tag used by the completion and error triggers.", '"ollama-status"');
AddAction(5, 0, "Check Ollama", "Ollama", "Check local Ollama status (tag <i>{0}</i>)", "Check whether Ollama is running and retrieve its installed model list.", "CheckOllama");
AddStringParam("Tag", "A tag used by the completion and error triggers.", '"ollama-chat"');
AddStringParam("Model", "An installed local Ollama model name.", '""');
AddStringParam("Prompt", "Prompt to send to the selected local model.", '""');
AddStringParam("System prompt", "Optional system instructions.", '"You are a careful Construct 2 debugging assistant. Ground claims in supplied project evidence."');
AddAction(6, 0, "Chat with Ollama", "Ollama", "Send prompt to model <b>{1}</b> (tag <i>{0}</i>)", "Submit a user-requested prompt to a local Ollama model.", "ChatWithOllama");
AddAction(7, 0, "Cancel requests", "Requests", "Cancel pending requests", "Abort all requests currently in progress.", "CancelRequests");

AddStringParam("Tag", "Tag used by the On AI response and On error triggers.", '"browser-ai"');
AddComboParamOption("Any connected AI");
AddComboParamOption("ChatGPT");
AddComboParamOption("Claude");
AddComboParamOption("Gemini");
AddComboParam("Provider", "Choose which signed-in browser AI should receive the prompt.");
AddStringParam("Prompt", "Prompt to send through the browser connector.", '""');
AddStringParam("System prompt", "Optional role/instruction prefix to include in the prompt.", '""');
AddComboParamOption("No");
AddComboParamOption("Yes");
AddComboParam("Include project context", "Append the currently loaded project AI context to the prompt.");
AddAction(8, 0, "Send to Browser AI", "Browser AI", "Send prompt to <b>{1}</b> (tag <i>{0}</i>)", "Queue a prompt for the signed-in browser connector. You must submit it on the AI website and return the visible reply.", "SendToBrowserAI");

// Expressions
AddExpression(0, ef_return_string, "Last response", "Results", "Response", "Get the last response text or serialized JSON result.");
AddExpression(1, ef_return_string, "Last error", "Results", "Error", "Get the most recent error message.");
AddExpression(2, ef_return_string, "Last request ID", "Results", "RequestID", "Get the ID of the most recently started request.");
AddExpression(3, ef_return_string, "Base URL", "Connection", "BaseURL", "Get the configured local bridge URL.");
AddExpression(4, ef_return_string, "Project context", "Project", "ProjectContext", "Get the most recently retrieved AI context string.");
AddExpression(5, ef_return_string, "Ollama models", "Ollama", "OllamaModels", "Get the installed Ollama model list as JSON.");
AddExpression(6, ef_return_string, "Project SHA-256", "Project", "ProjectSHA256", "Get the hash returned when the project was opened.");
AddExpression(7, ef_return_string, "Selected model", "Ollama", "SelectedModel", "Get the model used by the last Ollama request.");
AddExpression(8, ef_return_string, "AI response", "Browser AI", "AIResponse", "Get the latest response returned through the browser connector.");
AddExpression(9, ef_return_string, "Request tag", "Results", "RequestTag", "Get the tag associated with the latest response or error.");

ACESDone();

var property_list = [
	new cr.Property(ept_text, "Base URL", "http://127.0.0.1:8765", "Loopback address of the local Construct 2 AI Bridge service.")
];

function CreateIDEObjectType()
{
	return new IDEObjectType();
}

function IDEObjectType()
{
	assert2(this instanceof arguments.callee, "Constructor called as a function");
}

IDEObjectType.prototype.CreateInstance = function(instance)
{
	return new IDEInstance(instance, this);
};

function IDEInstance(instance, type)
{
	assert2(this instanceof arguments.callee, "Constructor called as a function");
	this.instance = instance;
	this.type = type;
	this.properties = {};
	for (var i = 0; i < property_list.length; i++)
		this.properties[property_list[i].name] = property_list[i].initial_value;
}

IDEInstance.prototype.OnCreate = function() {};
IDEInstance.prototype.OnPropertyChanged = function(property_name) {};
IDEInstance.prototype.Draw = function(renderer) {};
IDEInstance.prototype.OnRendererReleased = function() {};
