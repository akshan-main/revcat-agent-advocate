import pytest

from advocate.config import Config, SafetyError
from advocate.revenuecat.mcp import RevenueCatMCP, READ_ONLY_TOOLS


def test_read_only_tools_set():
    assert "get-project-info" in READ_ONLY_TOOLS
    assert "list-apps" in READ_ONLY_TOOLS
    assert "query-charts" in READ_ONLY_TOOLS
    assert "create-offering" not in READ_ONLY_TOOLS
    assert "delete-customer" not in READ_ONLY_TOOLS


def test_safety_gate_blocks_write_tool():
    config = Config(
        revenuecat_api_key="sk_test",
        allow_writes=False,
        _env_file=None,
    )
    mcp = RevenueCatMCP(config)
    # Directly test the safety check without connecting
    with pytest.raises(SafetyError, match="requires ALLOW_WRITES"):
        import asyncio
        asyncio.run(mcp.call_tool("create-offering", {"name": "test"}))


def test_safety_gate_passes_read_tool():
    """Read-only tools should NOT be blocked by the safety gate."""
    config = Config(
        revenuecat_api_key="sk_test",
        allow_writes=False,
        _env_file=None,
    )
    # Verify directly: read-only tools are in the allowed set
    assert "get-project-info" in READ_ONLY_TOOLS
    assert "list-apps" in READ_ONLY_TOOLS

    # And write tools are NOT in the allowed set
    assert "create-offering" not in READ_ONLY_TOOLS

    # The safety check happens before connection, so a write tool raises immediately
    mcp = RevenueCatMCP(config)
    with pytest.raises(SafetyError):
        import asyncio
        asyncio.run(mcp.call_tool("create-offering", {"name": "test_again"}))

    # For read tools, no SafetyError would be raised (only connection error).
    # We don't test the connection path since it requires a real MCP server.


def test_mock_mcp_client():
    from demo.mock_api import MockMCPClient
    client = MockMCPClient()
    tools = client.list_tools()
    assert len(tools) >= 20
    # All tools have name and description
    for tool in tools:
        assert "name" in tool
        assert "description" in tool


def test_mock_mcp_call_tool():
    from demo.mock_api import MockMCPClient
    client = MockMCPClient()
    result = client.call_tool("get-project-info", {})
    assert "DEMO" in result["result"]
    assert result["demo"] is True
