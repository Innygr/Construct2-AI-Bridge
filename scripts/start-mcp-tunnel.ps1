# Start the authenticated local MCP endpoint for a Cloudflare Quick Tunnel.
$ErrorActionPreference = "Stop"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "cloudflared was not found. Install Cloudflare Tunnel (cloudflared) and reopen PowerShell."
}

Write-Host "Forwarding HTTPS tunnel traffic to the loopback-only MCP server at http://127.0.0.1:8766"
Write-Host "Keep the Construct 2 AI Bridge and its MCP HTTP server running in separate terminals."
Write-Host "The Quick Tunnel URL is temporary and changes when restarted."
cloudflared tunnel --url http://127.0.0.1:8766
