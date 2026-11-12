# ChatGPT and MCP integration

The MCP adapter exposes the existing local bridge to compatible AI clients. It does not replace the browser extension, project reader, or approval-based XML writer.

## Install and start

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Start the existing local API/UI in terminal 1:

```powershell
construct2-ai-bridge
```

Open a Construct 2 `.capx` or `.caproj` in the UI at http://127.0.0.1:8765.

## Local MCP (stdio)

For a local MCP-capable desktop client, register this server command:

```json
{
  "mcpServers": {
    "construct2-ai-bridge": {
      "type": "stdio",
      "command": "construct2-ai-bridge-mcp",
      "args": []
    }
  }
}
```

The MCP process communicates with the already-running API on 127.0.0.1:8765. If the executable is not on the host PATH, use the full path to the Python environment's `construct2-ai-bridge-mcp` executable, or use `python -m construct2_ai_bridge.mcp_adapter`.

## ChatGPT web through an HTTPS tunnel

The web connector needs a publicly reachable HTTPS MCP endpoint. The adapter provides a separate Streamable HTTP server on loopback port 8766 and requires a bearer token. Do not tunnel the regular API/UI port 8765.

Start the authenticated MCP HTTP server in terminal 2:

```powershell
construct2-ai-bridge-mcp --transport http
```

On first launch it creates a private bearer token file:
- Windows: `%APPDATA%\construct2-ai-bridge\mcp-token`
- Linux: `~/.config/construct2-ai-bridge/mcp-token`

Keep this token private. It is not written to the project or printed to the terminal.

Install Cloudflare Tunnel (`cloudflared`) and start a Quick Tunnel in terminal 3:

```powershell
cloudflared tunnel --url http://127.0.0.1:8766
```

Or run `scripts/start-mcp-tunnel.ps1`. Cloudflare prints a temporary HTTPS hostname. The MCP endpoint is that hostname plus `/mcp`. The HTTP MCP server requires `Authorization: Bearer <token>` on every request.

Quick Tunnel hostnames are temporary and change after restart. For a stable ChatGPT connection, configure a named Cloudflare Tunnel with a hostname on a domain you control, routing only to `http://127.0.0.1:8766`. Keep the bearer token enabled. Never expose port 8765 through the tunnel.

Once the HTTPS hostname exists, add the remote MCP server to the ChatGPT connector configuration with:
- Transport: Streamable HTTP
- URL: `https://YOUR-TUNNEL-HOST/mcp`
- Authentication: API key / Bearer
- Secret: contents of the local MCP token file

The hostname and token are user-specific setup values. Do not commit them to Git or include them in the plugin package. The plugin package's local stdio entry remains available for desktop clients; the remote endpoint is what enables ChatGPT web.

## Tools

Read tools:
- `bridge_status`
- `get_project_state` (provide an XML document name to obtain the current project hash)
- `get_project_summary`
- `get_objects`
- `get_event_sheets`
- `get_event_details`
- `get_ai_context`
- `get_project_xml`
- `get_xml_tree`

Write workflow:
1. Call `propose_xml_patch` to return a non-mutating proposal, current XML tree, and project hash.
2. Review the proposed operations and explain the intended change.
3. Obtain explicit user approval.
4. Call `apply_approved_patch` with the exact project hash, approved operations, and `user_approved=true`.

Writes continue through the existing API validation, stale-hash check, numbered backup, and atomic replacement. The adapter never executes Construct 2 project content. Event/XML inspection remains best-effort; verify changes in Construct 2.

## Security notes

- Both the API and MCP HTTP server bind to loopback only.
- The tunnel must target port 8766 only. The MCP endpoint is protected by a random bearer token.
- Treat the tunnel hostname and bearer token as credentials; do not publish them.
- Only connect trusted AI clients and review project context before sharing it.
- A successful tunnel does not mean ChatGPT has been connected yet; add the returned HTTPS endpoint to the ChatGPT connector after tunnel setup.
