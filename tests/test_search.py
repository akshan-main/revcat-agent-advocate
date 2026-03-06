import os

from advocate.knowledge.search import (
    tokenize, build_index, search, _bm25_score,
    get_citation_url, format_citations, SearchIndex,
)


def test_tokenize_basic():
    tokens = tokenize("Hello World! This is a test.")
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens
    # Stopwords removed
    assert "this" not in tokens
    assert "is" not in tokens


def test_tokenize_removes_short():
    tokens = tokenize("I a am x y RevenueCat")
    assert "revenuecat" in tokens
    assert "am" in tokens  # 2 chars, passes length check
    # Single chars removed
    assert "i" not in tokens
    assert "a" not in tokens
    assert "x" not in tokens


def test_build_index(sample_docs_cache):
    index = build_index(sample_docs_cache)
    assert index.doc_count == 3
    assert index.avg_doc_length > 0
    assert len(index.inverted_index) > 0


def test_search_charts(sample_docs_cache):
    index = build_index(sample_docs_cache)
    results = search("charts metrics MRR", index, sample_docs_cache)
    assert len(results) > 0
    # Charts doc should rank first
    assert "charts" in results[0].title.lower() or "charts" in results[0].path.lower()


def test_search_returns_sha256(sample_docs_cache, db_conn):
    # Store a snapshot so sha256 is available
    from advocate.knowledge.ingest import store_snapshot, DocEntry
    entry = DocEntry(
        path="dashboard-and-metrics/charts",
        title="Charts",
        category="Dashboard",
        url="https://www.revenuecat.com/docs/dashboard-and-metrics/charts",
    )
    store_snapshot(db_conn, entry, "test_sha256", 500)

    index = build_index(sample_docs_cache, db_conn)
    results = search("charts", index, sample_docs_cache)
    # The charts result should have the sha256
    charts_result = [r for r in results if "charts" in r.path.lower()]
    assert len(charts_result) > 0
    assert charts_result[0].doc_sha256 == "test_sha256"


def test_bm25_scoring():
    score = _bm25_score(
        term_freq=3, doc_length=100, avg_doc_length=200,
        doc_freq=5, total_docs=100,
    )
    assert score > 0

    # Higher term freq should give higher score
    score_high = _bm25_score(
        term_freq=10, doc_length=100, avg_doc_length=200,
        doc_freq=5, total_docs=100,
    )
    assert score_high > score


def test_search_empty_query(sample_docs_cache):
    index = build_index(sample_docs_cache)
    results = search("", index, sample_docs_cache)
    assert results == []


def test_get_citation_url():
    assert get_citation_url("dashboard-and-metrics__charts") == "https://www.revenuecat.com/docs/dashboard-and-metrics/charts"


def test_format_citations():
    from advocate.models import SearchResult
    results = [
        SearchResult(url="https://example.com/a", path="a", title="Doc A", score=1.0, doc_sha256=""),
        SearchResult(url="https://example.com/b", path="b", title="Doc B", score=0.5, doc_sha256=""),
    ]
    md = format_citations(results)
    assert "## Sources" in md
    assert "[Doc A]" in md
    assert "[Doc B]" in md


def test_format_citations_empty():
    assert format_citations([]) == ""
