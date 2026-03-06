import os

from advocate.content.planner import suggest_topics, create_outline
from advocate.content.writer import (
    generate_draft, save_draft, extract_code_snippets,
    save_code_snippets, extract_citations, build_source_citations,
    record_content,
)
from advocate.models import ContentOutline, ContentType, ContentPiece, SearchResult, Section


def _make_search_results():
    return [
        SearchResult(
            url="https://www.revenuecat.com/docs/dashboard-and-metrics/charts",
            path="dashboard-and-metrics/charts",
            title="Charts Overview",
            score=5.0,
            snippets=["Charts help you track MRR", "Available metrics include churn"],
            doc_sha256="sha_charts",
        ),
        SearchResult(
            url="https://www.revenuecat.com/docs/api-v2",
            path="api-v2",
            title="REST API v2",
            score=3.0,
            snippets=["The REST API v2 uses Bearer token auth"],
            doc_sha256="sha_api",
        ),
    ]


def test_suggest_topics():
    topics = suggest_topics(count=3)
    assert len(topics) == 3
    for topic in topics:
        assert isinstance(topic, str)
        assert len(topic) > 10


def test_create_outline_from_results():
    results = _make_search_results()
    outline = create_outline("Charts API Tutorial", ContentType.TUTORIAL, results)
    assert outline.title == "Charts API Tutorial"
    assert outline.content_type == ContentType.TUTORIAL
    assert len(outline.sections) >= 3  # intro + results + takeaways
    assert len(outline.sources) > 0


def test_outline_has_source_refs():
    results = _make_search_results()
    outline = create_outline("Test Topic", ContentType.TUTORIAL, results)
    # At least some sections should have source refs
    has_refs = any(len(s.source_refs) > 0 for s in outline.sections)
    assert has_refs


def test_generate_draft_from_template():
    outline = ContentOutline(
        title="Test Article",
        content_type=ContentType.TUTORIAL,
        sections=[
            Section(
                heading="Introduction",
                key_points=["Point A", "Point B"],
                source_refs=["https://www.revenuecat.com/docs/charts"],
            ),
            Section(
                heading="Details",
                key_points=["Detail 1"],
                source_refs=["https://www.revenuecat.com/docs/api-v2"],
            ),
        ],
        sources=["https://www.revenuecat.com/docs/charts"],
        estimated_word_count=500,
    )
    doc_snippets = {"https://www.revenuecat.com/docs/charts": "# Charts\nMetrics overview."}
    body = generate_draft(outline, doc_snippets)
    assert "# Test Article" in body
    assert "## Sources" in body
    assert "[Source]" in body
    assert "---" in body  # YAML front matter


def test_extract_code_snippets():
    md = """# Test
Some text.
```python
print("hello")
```
More text.
```javascript
console.log("world");
```
"""
    snippets = extract_code_snippets(md)
    assert len(snippets) == 2
    assert snippets[0] == ("python", 'print("hello")')
    assert snippets[1] == ("javascript", 'console.log("world");')


def test_extract_citations():
    md = """
[Source](https://www.revenuecat.com/docs/charts)
Some text with [link](https://www.revenuecat.com/docs/api-v2).
"""
    urls = extract_citations(md)
    assert "https://www.revenuecat.com/docs/charts" in urls
    assert "https://www.revenuecat.com/docs/api-v2" in urls


def test_save_draft(tmp_path):
    body = "# Test\nContent"
    path = save_draft(body, "test-post", str(tmp_path))
    assert os.path.exists(path)
    with open(path) as f:
        assert f.read() == body


def test_save_code_snippets(tmp_path):
    snippets = [("python", "print(1)"), ("javascript", "console.log(1)")]
    paths = save_code_snippets(snippets, "test-post", str(tmp_path))
    assert len(paths) == 2
    assert paths[0].endswith(".py")
    assert paths[1].endswith(".js")


def test_build_source_citations():
    body = "[Source](https://www.revenuecat.com/docs/charts) and [another](https://www.revenuecat.com/docs/api-v2)"
    doc_snippets = {"https://www.revenuecat.com/docs/charts": "# Charts content"}
    citations = build_source_citations(body, doc_snippets)
    assert len(citations) == 2
    # The one with content should have a sha256
    charts_cit = [c for c in citations if "charts" in c.url]
    assert len(charts_cit) == 1
    assert charts_cit[0].doc_sha256 != ""


def test_record_content(db_conn):
    piece = ContentPiece(
        slug="test-record",
        title="Test Record",
        content_type=ContentType.TUTORIAL,
        status="draft",
        body_md="# Test",
        created_at="2026-01-01T00:00:00Z",
        word_count=100,
        citations_count=5,
    )
    row_id = record_content(db_conn, piece)
    assert row_id > 0

    from advocate.db import query_rows
    rows = query_rows(db_conn, "content_pieces", where={"slug": "test-record"})
    assert len(rows) == 1
    assert rows[0]["title"] == "Test Record"
