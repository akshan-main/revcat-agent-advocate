import asyncio
from ..config import Config, SafetyError

MCP_ENDPOINT = "https://mcp.revenuecat.ai/mcp"

# Tools safe to call without ALLOW_WRITES
READ_ONLY_TOOLS = {
    "get-project-info", "list-apps", "list-products",
    "list-offerings", "list-entitlements", "get-customer",
    "query-charts", "list-subscribers", "get-subscriber",
    "list-packages", "get-offering", "get-app",
}


class RevenueCatMCP:
    """MCP client using the official mcp Python SDK with Streamable HTTP transport."""

    def __init__(self, config: Config):
        self.config = config
        self.endpoint = MCP_ENDPOINT
        self._session = None
        self._streams = None

    async def connect(self):
        """Initialize MCP session via Streamable HTTP."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = {"Authorization": f"Bearer {self.config.revenuecat_api_key}"}
        self._streams = streamablehttp_client(self.endpoint, headers=headers)
        read_stream, write_stream, _ = await self._streams.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

    async def list_tools(self) -> list[dict]:
        """Discover all RC MCP tools."""
        if not self._session:
            await self.connect()
        result = await self._session.list_tools()
        return [{"name": t.name, "description": t.description or ""} for t in result.tools]

    async def call_tool(self, name: str, params: dict) -> dict:
        """Call a specific MCP tool with safety gate."""
        if name not in READ_ONLY_TOOLS and not self.config.allow_writes:
            raise SafetyError(f"MCP tool '{name}' requires ALLOW_WRITES=true")
        if not self._session:
            await self.connect()
        result = await self._session.call_tool(name, params)
        # Extract text content from result
        content_parts = []
        for part in result.content:
            if hasattr(part, "text"):
                content_parts.append(part.text)
        return {"result": "\n".join(content_parts) if content_parts else str(result)}

    async def disconnect(self):
        """Close MCP session."""
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._streams:
            await self._streams.__aexit__(None, None, None)
            self._streams = None


def run_mcp_sync(config: Config, tool_name: str, params: dict) -> dict:
    """Synchronous wrapper around async MCP calls."""
    async def _run():
        client = RevenueCatMCP(config)
        try:
            await client.connect()
            return await client.call_tool(tool_name, params)
        finally:
            await client.disconnect()
    return asyncio.run(_run())


def list_mcp_tools_sync(config: Config) -> list[dict]:
    """Synchronous wrapper to discover MCP tools."""
    async def _run():
        client = RevenueCatMCP(config)
        try:
            await client.connect()
            return await client.list_tools()
        finally:
            await client.disconnect()
    return asyncio.run(_run())
