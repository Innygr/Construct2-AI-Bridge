#!/usr/bin/env sh
set -eu
command -v cloudflared >/dev/null 2>&1 || {
  echo "cloudflared was not found. Install Cloudflare Tunnel first." >&2
  exit 1
}
echo "Forwarding HTTPS tunnel traffic to loopback-only MCP server at http://127.0.0.1:8766"
echo "Keep the Construct 2 AI Bridge and its MCP HTTP server running in separate terminals."
echo "The Quick Tunnel URL is temporary and changes when restarted."
exec cloudflared tunnel --url http://127.0.0.1:8766
