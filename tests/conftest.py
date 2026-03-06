import os
import pytest

from advocate.config import Config
from advocate.db import init_db


@pytest.fixture
def db_conn():
    """In-memory SQLite with schema initialized."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def mock_config(tmp_path):
    """Config with test values, demo mode on."""
    return Config(
        demo_mode=True,
        dry_run=True,
        allow_writes=False,
        db_path=str(tmp_path / "test.db"),
        docs_cache_dir=str(tmp_path / "docs"),
        site_output_dir=str(tmp_path / "site"),
        runs_dir=str(tmp_path / "runs"),
        _env_file=None,
    )


@pytest.fixture
def sample_docs_cache(tmp_path):
    """Temp dir with sample cached doc pages."""
    cache = tmp_path / "docs" / "pages"
    cache.mkdir(parents=True)
    (cache / "dashboard-and-metrics__charts.md").write_text(
        "# Charts\n\nRevenueCat Charts provide a real-time view of your subscription metrics.\n\n"
        "## Available Metrics\n\nMRR, Active Subscriptions, Churn, Revenue, Trials.\n\n"
        "## Using the Charts API\n\nYou can query charts data using the REST API v2.\n"
    )
    (cache / "projects__authentication.md").write_text(
        "# Authentication\n\nRevenueCat uses API keys to authenticate requests.\n\n"
        "## API Key Types\n\nSecret API Keys (sk_) and App-Specific API Keys (atk_).\n\n"
        "## REST API v2 Authentication\n\nAuthorization: Bearer sk_your_secret_key_here\n"
    )
    (cache / "tools__mcp.md").write_text(
        "# RevenueCat MCP Server\n\nThe MCP server exposes 26 tools for AI agents.\n\n"
        "## Endpoint\n\nhttps://mcp.revenuecat.ai/mcp\n\n"
        "## Setting Up with Claude Code\n\nclaude mcp add revenuecat -t http\n"
    )
    return str(tmp_path / "docs")


@pytest.fixture
def sample_index_text():
    """Subset of real LLM index for testing."""
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    with open(os.path.join(fixtures_dir, "sample_index.txt")) as f:
        return f.read()
