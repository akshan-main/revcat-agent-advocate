"""Integration test: run the full demo pipeline and verify outputs."""

import json
import os
import re
import shutil

import responses

from click.testing import CliRunner

# This test uses responses to mock all HTTP calls


@responses.activate(assert_all_requests_are_fired=False)
def test_demo_run_full_pipeline(tmp_path, monkeypatch):
    """Run demo-run and verify all expected outputs exist."""
    # Set env vars for isolated test
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DOCS_CACHE_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("SITE_OUTPUT_DIR", str(tmp_path / "site"))
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    # Isolate from real cloud services (override .env file values)
    monkeypatch.setenv("TURSO_DATABASE_URL", "")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    monkeypatch.setenv("CHROMA_API_KEY", "")
    monkeypatch.setenv("HF_TOKEN", "")

    # Set up fixtures as cached docs to avoid HTTP calls during ingest
    docs_dir = tmp_path / "docs"
    pages_dir = docs_dir / "pages"
    pages_dir.mkdir(parents=True)

    # Copy sample docs to the cache location
    fixtures_dir = os.path.join(os.path.dirname(__file__), "..", "demo", "fixtures")
    for name in ["sample_doc_charts.md", "sample_doc_auth.md", "sample_doc_mcp.md",
                  "sample_doc_getting_started.md", "sample_doc_offerings.md"]:
        src = os.path.join(fixtures_dir, name)
        if os.path.exists(src):
            # Map to the expected cache filename pattern
            cache_name = name.replace("sample_doc_", "").replace(".md", "") + ".md"
            shutil.copy(src, str(pages_dir / cache_name))

    # Mock the LLM index fetch
    index_path = os.path.join(fixtures_dir, "sample_index.txt")
    with open(index_path) as f:
        index_content = f.read()

    responses.add(
        responses.GET,
        "https://www.revenuecat.com/docs/assets/files/llms-b3277dc1a771ac4b43dc7cfb88ebd955.txt",
        body=index_content,
        status=200,
    )

    # Mock all doc page fetches with a regex pattern
    responses.add(
        responses.GET,
        re.compile(r"https://www\.revenuecat\.com/docs/.*"),
        body="# Doc Page\nContent here.",
        status=200,
    )

    from cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["demo-run"], catch_exceptions=False)

    # Always print output for debugging
    print(result.output)

    site_dir = str(tmp_path / "site")
    runs_dir = str(tmp_path / "runs")

    # Debug: list what site files actually exist
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            print(f"  SITE: {os.path.join(root, f)}")

    # Verify site outputs exist
    assert os.path.exists(os.path.join(site_dir, "apply", "index.html")), "Apply page missing"
    assert os.path.exists(os.path.join(site_dir, "ledger", "index.html")), "Ledger page missing"
    assert os.path.exists(os.path.join(site_dir, "content", "index.html")), "Content index missing"
    assert os.path.exists(os.path.join(site_dir, "experiments", "index.html")), "Experiments page missing"
    assert os.path.exists(os.path.join(site_dir, "feedback", "index.html")), "Feedback page missing"
    assert os.path.exists(os.path.join(site_dir, "runbook", "index.html")), "Runbook page missing"

    # Verify run logs exist
    run_files = [f for f in os.listdir(runs_dir) if f.endswith(".json")]
    assert len(run_files) >= 7, f"Expected 7+ run files, got {len(run_files)}: {run_files}"

    # Verify each run file is valid JSON with required fields
    for rf in run_files:
        with open(os.path.join(runs_dir, rf)) as f:
            data = json.load(f)
        assert "run_id" in data
        assert "hash" in data
        assert "prev_hash" in data
        assert "command" in data

    # Verify chain integrity
    from advocate.db import init_db
    from advocate.ledger import verify_chain
    db = init_db(str(tmp_path / "test.db"))
    chain = verify_chain(db)
    assert chain.valid is True, f"Chain broken at: {chain.breaks}"
    assert chain.total_entries >= 7
    db.close()
