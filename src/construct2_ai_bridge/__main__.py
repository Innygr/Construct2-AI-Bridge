"""CLI entry point."""
import argparse
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn


def _open_window_when_ready(url: str, timeout: float = 15.0) -> None:
    """Open the UI in a new browser window after the local API responds."""
    deadline = time.monotonic() + timeout
    probe_url = url.rstrip("/") + "/api/status"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(probe_url, timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open_new(url)
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Construct 2 AI Bridge locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--window",
        action="store_true",
        help="open the local assistant UI in a separate browser window when ready",
    )
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("For safety, this version only permits loopback binding.")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")

    if args.window:
        url = f"http://{args.host if args.host != '::1' else '[::1]'}:{args.port}"
        threading.Thread(
            target=_open_window_when_ready,
            args=(url,),
            name="construct2-ai-bridge-window",
            daemon=True,
        ).start()

    uvicorn.run(
        "construct2_ai_bridge.server:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
