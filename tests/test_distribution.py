"""Tests for the distribution pipeline: queue, rate limiting, dedup."""
from advocate.distribution.pipeline import (
    enqueue,
    approve,
    skip,
    get_queue,
    check_rate_limit,
    record_post,
    record_failure,
    format_for_channel,
    preview_queue,
    init_distribution_db,
    DistributionItem,
)


def test_enqueue_and_get(db_conn):
    init_distribution_db(db_conn)
    item = DistributionItem(
        channel="github_comment",
        title="Test Post",
        body="This is a test response about RevenueCat subscriptions.",
    )
    item_id = enqueue(db_conn, item)
    assert item_id is not None

    queue = get_queue(db_conn)
    assert len(queue) == 1
    assert queue[0]["title"] == "Test Post"
    assert queue[0]["status"] == "draft"


def test_enqueue_dedup(db_conn):
    init_distribution_db(db_conn)
    item = DistributionItem(
        channel="github_comment",
        title="Duplicate",
        body="Same content repeated.",
    )
    id1 = enqueue(db_conn, item)
    id2 = enqueue(db_conn, item)
    assert id1 is not None
    assert id2 is None  # Duplicate rejected


def test_approve_and_skip(db_conn):
    init_distribution_db(db_conn)
    item = DistributionItem(channel="twitter", title="T", body="Tweet content")
    item_id = enqueue(db_conn, item)
    approve(db_conn, item_id)
    queue = get_queue(db_conn, status="approved")
    assert len(queue) == 1

    item2 = DistributionItem(channel="twitter", title="T2", body="Another tweet")
    item2_id = enqueue(db_conn, item2)
    skip(db_conn, item2_id, "not relevant")
    skipped = get_queue(db_conn, status="skipped")
    assert len(skipped) == 1


def test_rate_limit_default(db_conn):
    init_distribution_db(db_conn)
    allowed, reason = check_rate_limit(db_conn, "github_comment")
    assert allowed is True
    assert reason == "ok"


def test_record_post(db_conn):
    init_distribution_db(db_conn)
    item = DistributionItem(channel="github_comment", title="P", body="Posted content")
    item_id = enqueue(db_conn, item)
    approve(db_conn, item_id)
    record_post(db_conn, item_id, "https://github.com/issue/1#comment-1")
    posted = get_queue(db_conn, status="posted")
    assert len(posted) == 1
    assert posted[0]["post_url"] == "https://github.com/issue/1#comment-1"


def test_record_failure(db_conn):
    init_distribution_db(db_conn)
    item = DistributionItem(channel="twitter", title="F", body="Failed content")
    item_id = enqueue(db_conn, item)
    record_failure(db_conn, item_id, "API error 403")
    failed = get_queue(db_conn, status="failed")
    assert len(failed) == 1
    assert "403" in failed[0]["error"]


def test_format_for_twitter():
    content = "Check out [this guide](https://docs.revenuecat.com/test) for **details**!"
    formatted = format_for_channel(content, "twitter")
    assert "[" not in formatted  # Markdown links stripped
    assert "**" not in formatted  # Bold stripped
    assert len(formatted) <= 280


def test_format_for_github():
    content = "RevenueCat supports this feature."
    formatted = format_for_channel(content, "github_comment")
    assert "Advocate OS" in formatted  # Attribution footer


def test_format_for_reddit():
    content = "# Big Title\n\nContent here."
    formatted = format_for_channel(content, "reddit")
    assert not formatted.startswith("# ")  # H1 converted to H2


def test_preview_queue_empty(db_conn):
    init_distribution_db(db_conn)
    preview = preview_queue(db_conn)
    assert "empty" in preview.lower()


def test_preview_queue_with_items(db_conn):
    init_distribution_db(db_conn)
    enqueue(db_conn, DistributionItem(channel="twitter", title="Tweet 1", body="Content 1"))
    enqueue(db_conn, DistributionItem(channel="github_comment", title="GH 1", body="Content 2"))
    preview = preview_queue(db_conn)
    assert "Distribution Queue" in preview
    assert "twitter" in preview
    assert "github_comment" in preview
