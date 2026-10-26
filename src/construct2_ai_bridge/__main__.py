"""CLI entry point."""
import argparse
import uvicorn

def main() -> None:
    parser = argparse.ArgumentParser(description="Run Construct 2 AI Bridge locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("For safety, this version only permits loopback binding.")
    uvicorn.run("construct2_ai_bridge.server:app", host=args.host, port=args.port, log_level="info")

if __name__ == "__main__":
    main()
