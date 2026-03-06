import os
import tempfile

import pytest
import responses

from advocate.content.verifier import (
    verify_citations, verify_snippet_hashes, verify_doc_sha256,
    verify_code_snippets, full_verify,
)
from advocate.models import SourceCitation


@responses.activate
def test_verify_citations_reachable():
    responses.add(responses.HEAD, "https://www.revenuecat.com/docs/charts", status=200)
    responses.add(responses.HEAD, "https://www.revenuecat.com/docs/api-v2", status=200)

    body = "[Source](https://www.revenuecat.com/docs/charts) and [link](https://www.revenuecat.com/docs/api-v2)"
    reachable, dead = verify_citations(body, timeout=5)
    assert len(reachable) == 2
    assert len(dead) == 0


@responses.activate
def test_verify_citations_dead():
    responses.add(responses.HEAD, "https://www.revenuecat.com/docs/charts", status=200)
    responses.add(responses.HEAD, "https://www.revenuecat.com/docs/broken", status=404)

    body = "[Source](https://www.revenuecat.com/docs/charts) [broken](https://www.revenuecat.com/docs/broken)"
    reachable, dead = verify_citations(body, timeout=5)
    assert len(reachable) == 1
    assert len(dead) == 1
    assert "broken" in dead[0]


@responses.activate
def test_verify_citations_head_405_fallback():
    responses.add(responses.HEAD, "https://www.revenuecat.com/docs/test", status=405)
    responses.add(responses.GET, "https://www.revenuecat.com/docs/test", status=200, body="ok")

    body = "[Source](https://www.revenuecat.com/docs/test)"
    reachable, dead = verify_citations(body, timeout=5)
    assert len(reachable) == 1


def test_verify_snippet_hashes_valid(sample_docs_cache):
    # Quote text that exists in the cached docs
    body = "> RevenueCat Charts provide a real-time view of your subscription metrics"
    valid, invalid = verify_snippet_hashes(body, sample_docs_cache)
    assert len(valid) == 1
    assert len(invalid) == 0


def test_verify_snippet_hashes_invalid(sample_docs_cache):
    body = "> This text does not appear in any cached document at all ever"
    valid, invalid = verify_snippet_hashes(body, sample_docs_cache)
    assert len(valid) == 0
    assert len(invalid) == 1


def test_verify_doc_sha256_match(db_conn):
    db_conn.execute(
        "INSERT INTO doc_snapshots (url, path, doc_sha256, content_length, fetched_at) VALUES (?, ?, ?, ?, ?)",
        ["https://www.revenuecat.com/docs/charts", "charts", "sha_abc", 500, "2026-01-01"],
    )
    db_conn.commit()

    sources = [SourceCitation(url="https://www.revenuecat.com/docs/charts", doc_sha256="sha_abc")]
    matches, mismatches = verify_doc_sha256(sources, db_conn)
    assert len(matches) == 1
    assert len(mismatches) == 0


def test_verify_doc_sha256_mismatch(db_conn):
    db_conn.execute(
        "INSERT INTO doc_snapshots (url, path, doc_sha256, content_length, fetched_at) VALUES (?, ?, ?, ?, ?)",
        ["https://www.revenuecat.com/docs/charts", "charts", "sha_abc", 500, "2026-01-01"],
    )
    db_conn.commit()

    sources = [SourceCitation(url="https://www.revenuecat.com/docs/charts", doc_sha256="sha_DIFFERENT")]
    matches, mismatches = verify_doc_sha256(sources, db_conn)
    assert len(matches) == 0
    assert len(mismatches) == 1


def test_verify_code_snippets_valid_python(tmp_path):
    py_file = tmp_path / "snippet.py"
    py_file.write_text('print("hello")')
    valid, errors = verify_code_snippets([str(py_file)])
    assert len(valid) == 1
    assert len(errors) == 0


def test_verify_code_snippets_invalid_python(tmp_path):
    py_file = tmp_path / "bad.py"
    py_file.write_text("def broken(:\n  pass")
    valid, errors = verify_code_snippets([str(py_file)])
    assert len(valid) == 0
    assert len(errors) == 1


def test_verify_code_snippets_non_python(tmp_path):
    js_file = tmp_path / "snippet.js"
    js_file.write_text("console.log('hello');")
    valid, errors = verify_code_snippets([str(js_file)])
    assert len(valid) == 1  # Non-Python just checks file exists and non-empty


def test_full_verify(sample_docs_cache, db_conn):
    body = "# Article\n\nSome text.\n\n## Sources\n\n"
    result = full_verify(body, [], [], sample_docs_cache, db_conn, skip_network=True)
    assert result.citations_all_reachable is True
    assert result.snippet_syntax_valid is True
    assert result.doc_sha256_matches is True
    assert len(result.details) >= 3
