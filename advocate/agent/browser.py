"""Playwright MCP browser worker with requests fallback.

Domain-allowlisted, dry_run-gated.
"""
import asyncio
import shutil
from urllib.parse import urlparse

from ..config import Config


ALLOWED_DOMAINS = frozenset([
    "docs.revenuecat.com",
    "www.revenuecat.com",
    "community.revenuecat.com",
    "github.com",
    "dev.to",
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
    "stackoverflow.com",
    "revenuecat.com",
    "jobs.ashbyhq.com",
])

TIMEOUT_MS = 30_000


def _validate_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        return domain in ALLOWED_DOMAINS
    except Exception:
        return False


class PlaywrightMCPBrowser:
    """Connects to @playwright/mcp via stdio, exposes browser tools."""

    def __init__(self, config: Config):
        self.config = config
        self._session = None
        self._streams = None

    async def connect(self):
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client, StdioServerParameters
        except ImportError:
            raise ImportError("mcp SDK not installed")

        mcp_binary = shutil.which("mcp-server-playwright")
        server_params = StdioServerParameters(
            command=mcp_binary or "npx",
            args=["--headless"] if mcp_binary else ["@playwright/mcp@0.0.28", "--headless"],
        )
        self._streams = stdio_client(server_params)
        streams = await self._streams.__aenter__()
        read_stream, write_stream = streams
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

    async def disconnect(self):
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._streams:
            await self._streams.__aexit__(None, None, None)
            self._streams = None

    async def list_tools(self) -> list[dict]:
        if not self._session:
            raise RuntimeError("Not connected. Call connect() first.")
        result = await self._session.list_tools()
        return [{"name": t.name, "description": t.description} for t in result.tools]

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        if not self._session:
            raise RuntimeError("Not connected. Call connect() first.")
        # Enforce allowlist on any navigation tool call
        if name == "browser_navigate" and arguments:
            nav_url = arguments.get("url", "")
            if nav_url and not _validate_url(nav_url):
                return {"status": "blocked_domain", "domain": urlparse(nav_url).hostname, "url": nav_url}
        result = await self._session.call_tool(name, arguments or {})
        texts = []
        for block in result.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return {"status": "ok", "content": "\n".join(texts)}

    async def navigate(self, url: str) -> dict:
        if not _validate_url(url):
            return {"status": "blocked_domain", "domain": urlparse(url).hostname, "url": url}
        return await self.call_tool("browser_navigate", {"url": url})

    async def snapshot(self) -> dict:
        return await self.call_tool("browser_snapshot")

    async def get_visible_text(self) -> dict:
        return await self.call_tool("browser_snapshot")

    async def click(self, element: str, ref: str) -> dict:
        return await self.call_tool("browser_click", {"element": element, "ref": ref})

    async def type_text(self, element: str, ref: str, text: str) -> dict:
        return await self.call_tool("browser_type", {"element": element, "ref": ref, "text": text})

    async def screenshot(self) -> dict:
        return await self.call_tool("browser_screenshot")

    async def fetch_page_text(self, url: str) -> dict:
        nav_result = await self.navigate(url)
        if nav_result.get("status") != "ok":
            return nav_result

        snap_result = await self.snapshot()
        return {
            "status": "ok",
            "text": snap_result.get("content", "")[:50_000],
            "url": url,
            "method": "playwright_mcp",
        }


async def _mcp_fetch(url: str, config: Config) -> dict:
    browser = PlaywrightMCPBrowser(config)
    try:
        await browser.connect()
        return await browser.fetch_page_text(url)
    finally:
        await browser.disconnect()


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=TIMEOUT_MS / 1000 + 10)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def fetch_page_mcp(url: str, config: Config) -> dict:
    if not _validate_url(url):
        return {"status": "blocked_domain", "domain": urlparse(url).hostname, "url": url}
    if config.dry_run:
        return {"status": "blocked_dry_run", "url": url}

    try:
        return _run_async(_mcp_fetch(url, config))
    except Exception as e:
        return _fetch_with_requests(url, str(e))


def _fetch_with_requests(url: str, mcp_error: str = "") -> dict:
    import requests as req

    try:
        resp = req.get(url, timeout=15, headers={
            "User-Agent": "revcat-agent-advocate/1.0 (developer-advocate-bot)"
        })
        return {
            "status": "ok",
            "text": resp.text[:50_000],
            "title": "",
            "url": url,
            "method": "requests_fallback",
            "mcp_error": mcp_error,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "url": url}


def fetch_page(url: str, config: Config) -> dict:
    """Fetch page content. Tries Playwright MCP, falls back to requests."""
    if not _validate_url(url):
        return {"status": "blocked_domain", "domain": urlparse(url).hostname, "url": url}
    if config.dry_run:
        return {"status": "blocked_dry_run", "url": url}

    try:
        result = _run_async(_mcp_fetch(url, config))
        if result.get("status") == "ok":
            return result
    except Exception:
        pass

    return _fetch_with_requests(url)
