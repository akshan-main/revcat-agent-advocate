import pytest

from advocate.config import Config
from advocate.feedback.collector import (
    create_feedback, save_feedback, list_feedback,
    generate_feedback_from_docs,
)
from advocate.feedback.exporter import export_to_markdown, export_to_github_issue, export_batch
from advocate.models import ProductFeedback, Severity, FeedbackArea


def test_create_feedback_valid():
    fb = create_feedback(
        title="Test Issue",
        severity=Severity.MINOR,
        area=FeedbackArea.DOCS,
        repro_steps="Navigate to docs",
        expected="Clear docs",
        actual="Confusing docs",
    )
    assert fb.title == "Test Issue"
    assert fb.severity == Severity.MINOR
    assert fb.area == FeedbackArea.DOCS


def test_create_feedback_invalid_severity():
    with pytest.raises(ValueError):
        create_feedback(title="Test", severity="invalid_severity", area=FeedbackArea.DOCS)


def test_create_feedback_invalid_area():
    with pytest.raises(ValueError):
        create_feedback(title="Test", severity=Severity.MINOR, area="invalid_area")


def test_save_and_list_feedback(db_conn):
    fb = create_feedback(
        title="DB Test",
        severity=Severity.MAJOR,
        area=FeedbackArea.API,
    )
    row_id = save_feedback(db_conn, fb)
    assert row_id > 0

    items = list_feedback(db_conn)
    assert len(items) == 1
    assert items[0]["title"] == "DB Test"


def test_list_feedback_filters(db_conn):
    for i, area in enumerate([FeedbackArea.DOCS, FeedbackArea.API, FeedbackArea.DOCS]):
        fb = create_feedback(title=f"FB {area.value} {i}", severity=Severity.MINOR, area=area)
        save_feedback(db_conn, fb)

    docs_only = list_feedback(db_conn, area="docs")
    assert len(docs_only) == 2

    api_only = list_feedback(db_conn, area="api")
    assert len(api_only) == 1


def test_export_to_markdown():
    fb = ProductFeedback(
        title="Export Test",
        severity=Severity.CRITICAL,
        area=FeedbackArea.SDK,
        repro_steps="Step 1: Install SDK",
        expected="Works",
        actual="Crashes",
        evidence_links=["https://example.com/issue"],
        proposed_fix="Fix the crash",
    )
    md = export_to_markdown(fb)
    assert "# Export Test" in md
    assert "**Severity**: critical" in md
    assert "Step 1: Install SDK" in md
    assert "https://example.com/issue" in md


def test_export_to_github_issue_blocked_dry_run():
    config = Config(
        github_token="ghp_test",
        github_repo="user/repo",
        dry_run=True,
        _env_file=None,
    )
    fb = ProductFeedback(
        title="Test", severity=Severity.MINOR, area=FeedbackArea.DOCS,
    )
    result = export_to_github_issue(fb, config)
    assert result is None  # Blocked by dry_run


def test_export_to_github_issue_no_github():
    config = Config(dry_run=False, _env_file=None)
    fb = ProductFeedback(
        title="Test", severity=Severity.MINOR, area=FeedbackArea.DOCS,
    )
    result = export_to_github_issue(fb, config)
    assert result is None  # No github config


def test_feedback_requires_api_key():
    """Without API key, feedback generation raises RuntimeError."""
    with pytest.raises(RuntimeError, match="Anthropic API key required"):
        generate_feedback_from_docs(None, None, None, count=3)


def test_export_batch(db_conn, tmp_path):
    config = Config(dry_run=True, _env_file=None)
    for i in range(2):
        fb = create_feedback(
            title=f"Batch {i}",
            severity=Severity.MINOR,
            area=FeedbackArea.DOCS,
        )
        save_feedback(db_conn, fb)

    paths = export_batch(db_conn, config, output_dir=str(tmp_path))
    assert len(paths) == 2
    for p in paths:
        assert p.endswith(".md")
