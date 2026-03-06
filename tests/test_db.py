import json

from advocate.db import insert_row, query_rows, update_row, count_rows, rows_since, now_iso


def test_schema_creation(db_conn):
    tables = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {t["name"] for t in tables}
    assert "content_pieces" in table_names
    assert "growth_experiments" in table_names
    assert "community_interactions" in table_names
    assert "product_feedback" in table_names
    assert "run_log" in table_names
    assert "seo_pages" in table_names
    assert "doc_snapshots" in table_names


def test_insert_and_query_content(db_conn):
    row_id = insert_row(db_conn, "content_pieces", {
        "slug": "test-post",
        "title": "Test Post",
        "content_type": "tutorial",
        "status": "draft",
        "body_md": "# Test",
        "created_at": now_iso(),
    })
    assert row_id > 0

    rows = query_rows(db_conn, "content_pieces", where={"slug": "test-post"})
    assert len(rows) == 1
    assert rows[0]["title"] == "Test Post"


def test_insert_json_fields(db_conn):
    insert_row(db_conn, "run_log", {
        "run_id": "run_test_001",
        "sequence": 1,
        "command": "test",
        "started_at": now_iso(),
        "inputs_json": {"key": "value"},
        "sources_json": [{"url": "https://example.com"}],
        "prev_hash": "GENESIS",
        "hash": "abc123",
        "success": 1,
    })
    rows = query_rows(db_conn, "run_log", where={"run_id": "run_test_001"})
    assert len(rows) == 1
    # JSON fields are stored as strings
    inputs = json.loads(rows[0]["inputs_json"])
    assert inputs["key"] == "value"


def test_update_row(db_conn):
    row_id = insert_row(db_conn, "content_pieces", {
        "slug": "update-test",
        "title": "Original",
        "content_type": "tutorial",
        "status": "draft",
        "created_at": now_iso(),
    })
    update_row(db_conn, "content_pieces", row_id, {"title": "Updated", "status": "verified"})
    rows = query_rows(db_conn, "content_pieces", where={"slug": "update-test"})
    assert rows[0]["title"] == "Updated"
    assert rows[0]["status"] == "verified"


def test_count_rows(db_conn):
    assert count_rows(db_conn, "content_pieces") == 0
    insert_row(db_conn, "content_pieces", {
        "slug": "count-1", "title": "A", "content_type": "tutorial",
        "status": "draft", "created_at": now_iso(),
    })
    insert_row(db_conn, "content_pieces", {
        "slug": "count-2", "title": "B", "content_type": "case_study",
        "status": "draft", "created_at": now_iso(),
    })
    assert count_rows(db_conn, "content_pieces") == 2
    assert count_rows(db_conn, "content_pieces", where={"content_type": "tutorial"}) == 1


def test_rows_since(db_conn):
    old = "2020-01-01T00:00:00Z"
    insert_row(db_conn, "content_pieces", {
        "slug": "old-post", "title": "Old", "content_type": "tutorial",
        "status": "draft", "created_at": old,
    })
    insert_row(db_conn, "content_pieces", {
        "slug": "new-post", "title": "New", "content_type": "tutorial",
        "status": "draft", "created_at": now_iso(),
    })
    recent = rows_since(db_conn, "content_pieces", "2025-01-01T00:00:00Z")
    assert len(recent) == 1
    assert recent[0]["slug"] == "new-post"


def test_query_with_order_and_limit(db_conn):
    for i in range(5):
        insert_row(db_conn, "content_pieces", {
            "slug": f"post-{i}", "title": f"Post {i}", "content_type": "tutorial",
            "status": "draft", "created_at": now_iso(),
        })
    rows = query_rows(db_conn, "content_pieces", order_by="id ASC", limit=3)
    assert len(rows) == 3
    assert rows[0]["slug"] == "post-0"


def test_now_iso_format():
    ts = now_iso()
    assert "T" in ts
    assert ts.endswith("+00:00")
