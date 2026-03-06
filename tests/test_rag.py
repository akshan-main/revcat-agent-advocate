"""Tests for the RAG pipeline: ChromaDB vectors + HF Inference reranking + hybrid search."""
import os

import pytest

from advocate.knowledge.rag import (
    chunk_document,
    build_rag_index,
    semantic_search,
    hybrid_search,
    get_context_chunks,
    format_context,
    _split_by_headings,
    Chunk,
)

requires_hf = pytest.mark.skipif(
    not os.environ.get("HF_TOKEN"),
    reason="HF_TOKEN not set, skipping tests that require HF Inference API",
)


def test_split_by_headings():
    content = """# Title

Intro paragraph.

## Section One

Content of section one.

## Section Two

Content of section two.
"""
    sections = _split_by_headings(content)
    assert len(sections) >= 2
    assert sections[0][0] == "Title"
    assert "Intro" in sections[0][1]


def test_chunk_document():
    content = """# Test Doc

Introduction to the test document about RevenueCat subscriptions.

## First Section

This section has content about RevenueCat subscriptions and how they work
with various platforms including iOS, Android, and Flutter. The SDK makes it easy to
implement in-app purchases and manage subscription lifecycle events properly.

## Second Section

More content about the Charts API and how to query MRR, churn, LTV metrics.
The REST API v2 provides programmatic access to all chart data for analytics.
"""
    chunks = chunk_document(
        content, "test__doc.md",
        "https://www.revenuecat.com/docs/test/doc",
        "Test Doc", "sha256_test"
    )
    assert len(chunks) >= 2
    assert all(c.doc_url == "https://www.revenuecat.com/docs/test/doc" for c in chunks)
    assert all(c.doc_sha256 == "sha256_test" for c in chunks)


def test_chunk_document_merges_tiny():
    """Very short sections get merged."""
    content = """# Doc

Short intro.

## Tiny

Just a word.

## Real Section

This section has enough content to stand on its own with multiple sentences
and important information about subscriptions and monetization strategies.
"""
    chunks = chunk_document(content, "t.md", "url", "T", "sha")
    # The tiny section should be merged
    assert all(c.word_count >= 5 for c in chunks)


@requires_hf
def test_build_rag_index(sample_docs_cache):
    index = build_rag_index(sample_docs_cache)
    assert index.doc_count == 3
    assert index.chunk_count > 0
    assert index.collection is not None


@requires_hf
def test_semantic_search(sample_docs_cache):
    index = build_rag_index(sample_docs_cache)
    results = semantic_search("subscription metrics MRR churn", index, top_k=5)
    assert len(results) > 0
    # Charts doc chunks should rank high
    top_urls = [chunk.doc_url for chunk, _ in results[:3]]
    assert any("charts" in url for url in top_urls)


@requires_hf
def test_semantic_search_conceptual(sample_docs_cache):
    """Semantic search finds conceptually related content even with different words."""
    index = build_rag_index(sample_docs_cache)
    results = semantic_search("AI agent tools server", index, top_k=5)
    assert len(results) > 0
    top_urls = [chunk.doc_url for chunk, _ in results[:3]]
    assert any("mcp" in url for url in top_urls)


@requires_hf
def test_hybrid_search(sample_docs_cache):
    from advocate.knowledge.search import build_index
    bm25_index = build_index(sample_docs_cache)
    rag_index = build_rag_index(sample_docs_cache)

    results = hybrid_search(
        "charts API metrics",
        rag_index, bm25_index, sample_docs_cache, top_k=5,
    )
    assert len(results) > 0
    assert hasattr(results[0], "url")
    assert hasattr(results[0], "score")
    assert hasattr(results[0], "doc_sha256")


@requires_hf
def test_hybrid_search_combines_signals(sample_docs_cache):
    from advocate.knowledge.search import build_index
    bm25_index = build_index(sample_docs_cache)
    rag_index = build_rag_index(sample_docs_cache)

    # Exact keyword query
    r1 = hybrid_search("MRR", rag_index, bm25_index, sample_docs_cache, top_k=5)
    assert len(r1) > 0

    # Conceptual query
    r2 = hybrid_search("authenticate API requests", rag_index, bm25_index, sample_docs_cache, top_k=5)
    assert len(r2) > 0


@requires_hf
def test_get_context_chunks(sample_docs_cache):
    index = build_rag_index(sample_docs_cache)
    chunks = get_context_chunks("charts metrics", index, max_chunks=3, max_words=500)
    assert len(chunks) > 0
    assert len(chunks) <= 3


@requires_hf
def test_get_context_chunks_budget(sample_docs_cache):
    index = build_rag_index(sample_docs_cache)
    chunks = get_context_chunks("RevenueCat", index, max_chunks=20, max_words=50)
    total_words = sum(c.word_count for c in chunks)
    # Should roughly respect budget (allow flexibility for chunk granularity)
    assert total_words <= 200


def test_format_context():
    chunks = [
        Chunk(
            doc_path="test.md", doc_url="https://example.com/docs/test",
            doc_title="Test Doc", doc_sha256="abc123",
            heading="Section A", text="Content of section A.",
            word_count=5, chunk_index=0,
        ),
    ]
    formatted = format_context(chunks)
    assert "Source: https://example.com/docs/test" in formatted
    assert "Content of section A" in formatted
    assert "Section A" in formatted


def test_format_context_empty():
    assert format_context([]) == ""


def test_rag_index_empty_dir(tmp_path):
    index = build_rag_index(str(tmp_path))
    assert index.chunk_count == 0
    assert index.doc_count == 0


@requires_hf
def test_rag_index_with_db(sample_docs_cache, db_conn):
    from advocate.knowledge.ingest import store_snapshot, DocEntry
    entry = DocEntry(
        path="dashboard-and-metrics/charts",
        title="Charts",
        category="Dashboard",
        url="https://www.revenuecat.com/docs/dashboard-and-metrics/charts",
    )
    store_snapshot(db_conn, entry, "sha256_from_db", 500)

    index = build_rag_index(sample_docs_cache, db_conn)
    charts_chunks = [c for c in index.chunks if "charts" in c.doc_url]
    assert len(charts_chunks) > 0
    assert charts_chunks[0].doc_sha256 == "sha256_from_db"
