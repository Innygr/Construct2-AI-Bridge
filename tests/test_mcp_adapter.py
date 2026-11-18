"""Regression tests for the MCP transport's tunnel authentication."""
import asyncio

from construct2_ai_bridge.mcp_adapter import BearerTokenMiddleware


def test_bearer_middleware_rejects_missing_or_wrong_token():
    called = []

    async def app(scope, receive, send):
        called.append(True)

    async def run(headers):
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        middleware = BearerTokenMiddleware(app, "a" * 48)
        await middleware(
            {"type": "http", "method": "POST", "path": "/mcp", "headers": headers},
            receive,
            send,
        )
        return sent

    missing = asyncio.run(run([]))
    assert missing[0]["status"] == 401
    wrong = asyncio.run(run([(b"authorization", b"Bearer wrong")]))
    assert wrong[0]["status"] == 401
    assert called == []


def test_bearer_middleware_passes_valid_token():
    called = []

    async def app(scope, receive, send):
        called.append(scope["path"])

    async def run():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            pass

        middleware = BearerTokenMiddleware(app, "b" * 48)
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "headers": [(b"authorization", ("Bearer " + "b" * 48).encode())],
            },
            receive,
            send,
        )

    asyncio.run(run())
    assert called == ["/mcp"]
