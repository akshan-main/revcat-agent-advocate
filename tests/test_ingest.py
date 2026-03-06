import hashlib
import os

import pytest
import responses

from advocate.knowledge.ingest import (
    parse_index, fetch_doc_page, store_snapshot, _sanitize_path, DocEntry,
)


def test_parse_index(sample_index_text):
    entries = parse_index(sample_index_text)
    assert len(entries) == 20
    # Check first entry
    assert entries[0].title == "Welcome"
    assert entries[0].path == "welcome"
    assert entries[0].category == "Getting Started"


def test_parse_index_extracts_categories(sample_index_text):
    entries = parse_index(sample_index_text)
    categories = {e.category for e in entries}
    assert "Getting Started" in categories
    assert "API Reference" in categories
    assert "Tools" in categories


def test_parse_index_extracts_urls(sample_index_text):
    entries = parse_index(sample_index_text)
    for entry in entries:
        assert entry.url.startswith("https://www.revenuecat.com/docs/")


def test_sanitize_path():
    assert _sanitize_path("dashboard-and-metrics/charts") == "dashboard-and-metrics__charts"
    assert _sanitize_path("tools/mcp/tools-reference") == "tools__mcp__tools-reference"


@responses.activate
def test_fetch_doc_page_caches(tmp_path):
    entry = DocEntry(path="test/page", title="Test", category="Test", url="https://www.revenuecat.com/docs/test/page")
    cache_dir = str(tmp_path / "docs")

    responses.add(responses.GET, "https://www.revenuecat.com/docs/test/page.md",
                  body="# Test Page\nContent here.", status=200)

    content, sha = fetch_doc_page(entry, cache_dir, __import__("requests").Session())
    assert content == "# Test Page\nContent here."
    assert sha == hashlib.sha256(content.encode()).hexdigest()

    # Second call should use cache (no HTTP request)
    content2, sha2 = fetch_doc_page(entry, cache_dir, __import__("requests").Session())
    assert content2 == content
    assert sha2 == sha


@responses.activate
def test_fetch_doc_page_force(tmp_path):
    entry = DocEntry(path="test/force", title="Test", category="Test", url="https://www.revenuecat.com/docs/test/force")
    cache_dir = str(tmp_path / "docs")

    responses.add(responses.GET, "https://www.revenuecat.com/docs/test/force.md",
                  body="# Original", status=200)

    session = __import__("requests").Session()
    content1, _ = fetch_doc_page(entry, cache_dir, session)

    responses.reset()
    responses.add(responses.GET, "https://www.revenuecat.com/docs/test/force.md",
                  body="# Updated", status=200)

    content2, _ = fetch_doc_page(entry, cache_dir, session, force=True)
    assert content2 == "# Updated"


def test_store_snapshot_new(db_conn):
    entry = DocEntry(path="test/doc", title="Test", category="Test", url="https://www.revenuecat.com/docs/test/doc")
    store_snapshot(db_conn, entry, "sha256_abc", 1000)

    row = db_conn.execute("SELECT * FROM doc_snapshots WHERE url = ?", [entry.url]).fetchone()
    assert row is not None
    assert row["doc_sha256"] == "sha256_abc"
    assert row["changed_from"] is None


def test_store_snapshot_changed(db_conn):
    entry = DocEntry(path="test/doc", title="Test", category="Test", url="https://www.revenuecat.com/docs/test/doc")
    store_snapshot(db_conn, entry, "sha256_v1", 1000)
    store_snapshot(db_conn, entry, "sha256_v2", 1100)

    rows = db_conn.execute(
        "SELECT * FROM doc_snapshots WHERE url = ? ORDER BY fetched_at DESC", [entry.url]
    ).fetchall()
    # The latest should have changed_from set
    assert rows[0]["doc_sha256"] == "sha256_v2"
    assert rows[0]["changed_from"] == "sha256_v1"
