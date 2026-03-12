"""Tests for the Playwright MCP browser worker."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from advocate.agent.browser import (
    _validate_url,
    fetch_page,
    fetch_page_mcp,
    _fetch_with_requests,
    PlaywrightMCPBrowser,
    ALLOWED_DOMAINS,
)


# ── Domain Validation ──────────────────────────────────────────────

def test_validate_url_allowed():
    assert _validate_url("https://github.com/RevenueCat/purchases-ios/issues/1")
    assert _validate_url("https://www.revenuecat.com/docs/charts")
    assert _validate_url("https://dev.to/someuser/article")
    assert _validate_url("https://stackoverflow.com/questions/12345")


def test_validate_url_blocked():
    assert not _validate_url("https://evil.com/phish")
    assert not _validate_url("https://google.com")
    assert not _validate_url("https://malicious-site.io/exploit")


def test_validate_url_empty():
    assert not _validate_url("")
    assert not _validate_url("not-a-url")


def test_allowed_domains_coverage():
    """All expected domains are in the allowlist."""
    expected = {"github.com", "dev.to", "revenuecat.com", "www.revenuecat.com",
                "docs.revenuecat.com", "community.revenuecat.com",
                "reddit.com", "www.reddit.com", "old.reddit.com",
                "stackoverflow.com"}
    assert expected.issubset(ALLOWED_DOMAINS)


# ── Dry Run Gate ───────────────────────────────────────────────────

def test_fetch_page_blocked_dry_run(mock_config):
    """Dry run mode should block all fetches."""
    result = fetch_page("https://github.com/RevenueCat/test", mock_config)
    assert result["status"] == "blocked_dry_run"


def test_fetch_page_mcp_blocked_dry_run(mock_config):
    result = fetch_page_mcp("https://github.com/RevenueCat/test", mock_config)
    assert result["status"] == "blocked_dry_run"


# ── Domain Gate ────────────────────────────────────────────────────

def test_fetch_page_blocked_domain(mock_config):
    mock_config.dry_run = False
    result = fetch_page("https://evil.com/bad", mock_config)
    assert result["status"] == "blocked_domain"
    assert result["domain"] == "evil.com"


def test_fetch_page_mcp_blocked_domain(mock_config):
    mock_config.dry_run = False
    result = fetch_page_mcp("https://evil.com/bad", mock_config)
    assert result["status"] == "blocked_domain"


# ── Requests Fallback ─────────────────────────────────────────────

def test_fetch_with_requests_success():
    """Requests fallback should return page text."""
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.text = "<html>Hello World</html>"
        mock_get.return_value = mock_resp

        result = _fetch_with_requests("https://github.com/test")
        assert result["status"] == "ok"
        assert "Hello World" in result["text"]
        assert result["method"] == "requests_fallback"


def test_fetch_with_requests_error():
    """Requests fallback should handle errors gracefully."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")

        result = _fetch_with_requests("https://github.com/test")
        assert result["status"] == "error"
        assert "Connection refused" in result["error"]


def test_fetch_with_requests_truncates():
    """Should cap response at 50K chars."""
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.text = "x" * 100_000
        mock_get.return_value = mock_resp

        result = _fetch_with_requests("https://github.com/test")
        assert len(result["text"]) == 50_000


# ── Playwright MCP Browser Class ──────────────────────────────────

def test_playwright_mcp_browser_init(mock_config):
    browser = PlaywrightMCPBrowser(mock_config)
    assert browser.config == mock_config
    assert browser._session is None


@pytest.mark.asyncio
async def test_playwright_mcp_call_tool_not_connected(mock_config):
    """Should raise if not connected."""
    browser = PlaywrightMCPBrowser(mock_config)
    with pytest.raises(RuntimeError, match="Not connected"):
        await browser.call_tool("browser_navigate", {"url": "https://example.com"})


@pytest.mark.asyncio
async def test_playwright_mcp_list_tools_not_connected(mock_config):
    browser = PlaywrightMCPBrowser(mock_config)
    with pytest.raises(RuntimeError, match="Not connected"):
        await browser.list_tools()


@pytest.mark.asyncio
async def test_playwright_mcp_navigate_calls_tool(mock_config):
    """Navigate should call browser_navigate tool."""
    browser = PlaywrightMCPBrowser(mock_config)
    browser._session = AsyncMock()

    mock_content = MagicMock()
    mock_content.text = "Navigated to https://github.com/revenuecat"
    browser._session.call_tool.return_value = MagicMock(content=[mock_content])

    result = await browser.navigate("https://github.com/revenuecat")
    browser._session.call_tool.assert_called_once_with(
        "browser_navigate", {"url": "https://github.com/revenuecat"}
    )
    assert result["status"] == "ok"
    assert "Navigated" in result["content"]


@pytest.mark.asyncio
async def test_playwright_mcp_snapshot(mock_config):
    browser = PlaywrightMCPBrowser(mock_config)
    browser._session = AsyncMock()

    mock_content = MagicMock()
    mock_content.text = "Page accessibility tree content here"
    browser._session.call_tool.return_value = MagicMock(content=[mock_content])

    result = await browser.snapshot()
    browser._session.call_tool.assert_called_once_with("browser_snapshot", {})
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_playwright_mcp_click(mock_config):
    browser = PlaywrightMCPBrowser(mock_config)
    browser._session = AsyncMock()

    mock_content = MagicMock()
    mock_content.text = "Clicked element"
    browser._session.call_tool.return_value = MagicMock(content=[mock_content])

    result = await browser.click("Submit button", "ref123")
    browser._session.call_tool.assert_called_once_with(
        "browser_click", {"element": "Submit button", "ref": "ref123"}
    )
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_playwright_mcp_type_text(mock_config):
    browser = PlaywrightMCPBrowser(mock_config)
    browser._session = AsyncMock()

    mock_content = MagicMock()
    mock_content.text = "Typed text"
    browser._session.call_tool.return_value = MagicMock(content=[mock_content])

    await browser.type_text("Search input", "ref456", "RevenueCat")
    browser._session.call_tool.assert_called_once_with(
        "browser_type", {"element": "Search input", "ref": "ref456", "text": "RevenueCat"}
    )


@pytest.mark.asyncio
async def test_playwright_mcp_fetch_page_text(mock_config):
    """fetch_page_text should navigate then snapshot."""
    browser = PlaywrightMCPBrowser(mock_config)
    browser._session = AsyncMock()

    # First call: navigate, second call: snapshot
    nav_content = MagicMock()
    nav_content.text = "Navigated"
    snap_content = MagicMock()
    snap_content.text = "Page text with all the rendered content"

    browser._session.call_tool.side_effect = [
        MagicMock(content=[nav_content]),
        MagicMock(content=[snap_content]),
    ]

    result = await browser.fetch_page_text("https://github.com/test")
    assert result["status"] == "ok"
    assert result["method"] == "playwright_mcp"
    assert "rendered content" in result["text"]
    assert browser._session.call_tool.call_count == 2


# ── Integration: fetch_page with MCP fallback ─────────────────────

def test_fetch_page_falls_back_to_requests(mock_config):
    """When MCP fails, fetch_page should fall back to requests."""
    mock_config.dry_run = False

    with patch("advocate.agent.browser._run_async", side_effect=Exception("npx not found")):
        with patch("advocate.agent.browser._fetch_with_requests") as mock_req:
            mock_req.return_value = {
                "status": "ok",
                "text": "Fallback content",
                "method": "requests_fallback",
                "url": "https://github.com/test",
            }
            result = fetch_page("https://github.com/test", mock_config)
            assert result["status"] == "ok"
            assert result["method"] == "requests_fallback"
            mock_req.assert_called_once()
