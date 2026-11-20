"""The adapter exposes the read-only analysis tools next to the existing ones.

Needs the pinned MCP SDK (v1). Skipped when the SDK is missing or is a newer major
version whose API the adapter does not support.
"""
import asyncio

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="needs the pinned MCP SDK v1")
try:
    from construct2_ai_bridge import mcp_adapter
except ImportError:  # SDK present but incompatible with the adapter's imports
    pytest.skip("MCP SDK version is not supported by the adapter", allow_module_level=True)


def _tool_names() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp_adapter.mcp.list_tools())}


def test_analysis_tools_are_registered_alongside_existing_tools() -> None:
    names = _tool_names()
    assert {"explain_events", "lint_project"} <= names
    assert {"bridge_status", "get_project_summary", "propose_xml_patch", "apply_approved_patch"} <= names


def test_analysis_tools_do_not_add_a_write_path() -> None:
    names = _tool_names()
    writers = {n for n in names if any(word in n for word in ("write", "patch", "restore", "apply"))}
    assert writers == {"propose_xml_patch", "apply_approved_patch"}
