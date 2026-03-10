import os

from advocate.db import insert_row, now_iso
from advocate.site.generator import build_site, _md_to_html


def _setup_config(tmp_path):
    from advocate.config import Config
    config = Config(
        site_output_dir=str(tmp_path / "site"),
        runs_dir=str(tmp_path / "runs"),
        docs_cache_dir=str(tmp_path / "docs"),
        _env_file=None,
    )
    os.makedirs(config.site_output_dir, exist_ok=True)
    os.makedirs(config.runs_dir, exist_ok=True)
    return config


def test_build_site_creates_dirs(db_conn, tmp_path):
    config = _setup_config(tmp_path)
    build_site(db_conn, config)

    site_dir = config.site_output_dir
    assert os.path.exists(os.path.join(site_dir, "apply", "index.html"))
    assert os.path.exists(os.path.join(site_dir, "content", "index.html"))
    assert os.path.exists(os.path.join(site_dir, "experiments", "index.html"))
    assert os.path.exists(os.path.join(site_dir, "feedback", "index.html"))
    assert os.path.exists(os.path.join(site_dir, "runbook", "index.html"))


def test_build_site_index_redirect(db_conn, tmp_path):
    config = _setup_config(tmp_path)
    build_site(db_conn, config)

    with open(os.path.join(config.site_output_dir, "index.html")) as f:
        content = f.read()
    assert "/apply/" in content


def test_build_site_with_content(db_conn, tmp_path):
    config = _setup_config(tmp_path)

    # Add some content
    insert_row(db_conn, "content_pieces", {
        "slug": "test-post",
        "title": "Test Post",
        "content_type": "tutorial",
        "status": "verified",
        "body_md": "# Test Post\n\nSome content here.",
        "created_at": now_iso(),
    })

    build_site(db_conn, config)

    # Content detail page should exist
    detail_path = os.path.join(config.site_output_dir, "content", "test-post", "index.html")
    assert os.path.exists(detail_path)


def test_build_site_chain_status(db_conn, tmp_path):
    config = _setup_config(tmp_path)
    build_site(db_conn, config)

    with open(os.path.join(config.site_output_dir, "apply", "index.html")) as f:
        content = f.read()
    # Footer should show build info
    assert "revcat-agent-advocate" in content


def test_md_to_html_headers():
    # _md_to_html strips the leading H1 (template renders it separately)
    html = _md_to_html("# Title\n## Subtitle\n### Section")
    assert "<h2" in html
    assert "<h3" in html
    # Leading H1 is stripped, but a non-leading H1 is kept
    html2 = _md_to_html("## Intro\n# Later Title\n### Section")
    assert "<h1" in html2


def test_md_to_html_code_blocks():
    html = _md_to_html("```python\nprint('hi')\n```")
    assert "<pre><code" in html
    assert "print" in html


def test_md_to_html_links():
    html = _md_to_html("[Click here](https://example.com)")
    assert '<a href="https://example.com">' in html


def test_md_to_html_lists():
    html = _md_to_html("- Item 1\n- Item 2\n- Item 3")
    assert "<ul>" in html
    assert "<li>" in html
    assert "Item 1" in html


def test_md_to_html_bold_italic():
    html = _md_to_html("**bold** and *italic*")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html


def test_md_to_html_blockquote():
    html = _md_to_html("> This is a quote")
    assert "<blockquote>" in html


def test_build_site_returns_page_count(db_conn, tmp_path):
    config = _setup_config(tmp_path)
    count = build_site(db_conn, config)
    assert count >= 5  # at least: index, apply, content, experiments, feedback, runbook
