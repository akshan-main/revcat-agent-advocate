"""Tests for agent memory pruning."""
from datetime import datetime, timedelta, timezone

from advocate.db import insert_row, prune_memory


def _insert_lesson(db_conn, lesson_type="strategy", key="test-key", insight="test insight",
                   confidence=0.5, days_ago=0):
    """Helper to insert a lesson with a specific age."""
    created = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return insert_row(db_conn, "agent_memory", {
        "cycle_id": f"test_{days_ago}",
        "lesson_type": lesson_type,
        "key": key,
        "insight": insight,
        "evidence": "",
        "confidence": confidence,
        "created_at": created,
    })


def test_prune_removes_duplicates(db_conn):
    """Exact duplicates (same type+key+insight) should be deduplicated, keeping newest."""
    _insert_lesson(db_conn, key="dup", insight="same thing", days_ago=5)
    _insert_lesson(db_conn, key="dup", insight="same thing", days_ago=3)
    _insert_lesson(db_conn, key="dup", insight="same thing", days_ago=1)

    stats = prune_memory(db_conn)
    assert stats["duplicates_removed"] == 2
    remaining = db_conn.execute("SELECT * FROM agent_memory").fetchall()
    assert len(remaining) == 1


def test_prune_removes_old_low_confidence(db_conn):
    """Lessons older than max_age_days with confidence < threshold get removed."""
    _insert_lesson(db_conn, key="old-low", confidence=0.3, days_ago=100)
    _insert_lesson(db_conn, key="old-high", confidence=0.8, days_ago=100)
    _insert_lesson(db_conn, key="new-low", confidence=0.3, days_ago=10)

    stats = prune_memory(db_conn, max_age_days=90, min_confidence_old=0.7)
    assert stats["low_confidence_removed"] == 1
    remaining = db_conn.execute("SELECT key FROM agent_memory ORDER BY key").fetchall()
    keys = [r["key"] for r in remaining]
    assert "old-low" not in keys
    assert "old-high" in keys
    assert "new-low" in keys


def test_prune_keeps_recent_regardless_of_confidence(db_conn):
    """Recent lessons are always kept, even if confidence is low."""
    _insert_lesson(db_conn, key="recent-low", confidence=0.1, days_ago=5)

    stats = prune_memory(db_conn, max_age_days=90)
    assert stats["low_confidence_removed"] == 0
    assert stats["total_remaining"] == 1


def test_prune_enforces_max_per_type_key(db_conn):
    """Per (lesson_type, key) combo, keep only the newest N — but only for old lessons."""
    # 20 recent lessons (within 90 days) — all protected
    for i in range(20):
        _insert_lesson(db_conn, key="busy-key", insight=f"recent {i}", days_ago=i)
    # 10 old lessons (beyond 90 days) — subject to per-key cap
    for i in range(10):
        _insert_lesson(db_conn, key="busy-key", insight=f"old {i}", days_ago=100 + i, confidence=0.8)

    # max_per_type_key=20 means only 20 old ones allowed, but there are 20 recent + 10 old = 30 total
    # The per-key cap only prunes old lessons beyond the cap
    stats = prune_memory(db_conn, max_per_type_key=20)
    assert stats["excess_removed"] == 10
    assert stats["total_remaining"] == 20


def test_prune_per_key_cap_protects_recent(db_conn):
    """Recent lessons are never removed by the per-key cap, even if count exceeds max."""
    for i in range(25):
        _insert_lesson(db_conn, key="busy-key", insight=f"lesson {i}", days_ago=i)

    stats = prune_memory(db_conn, max_per_type_key=5)
    # All 25 are within 90 days, so none should be removed by per-key cap
    assert stats["excess_removed"] == 0
    assert stats["total_remaining"] == 25


def test_prune_dry_run_no_deletions(db_conn):
    """Dry run reports counts but doesn't actually delete."""
    _insert_lesson(db_conn, key="dup", insight="same", days_ago=1)
    _insert_lesson(db_conn, key="dup", insight="same", days_ago=2)
    _insert_lesson(db_conn, key="old", confidence=0.2, days_ago=120)

    stats = prune_memory(db_conn, dry_run=True)
    assert stats["total_removed"] > 0
    remaining = db_conn.execute("SELECT COUNT(*) as cnt FROM agent_memory").fetchone()
    assert remaining["cnt"] == 3  # nothing actually deleted


def test_prune_no_lessons_is_noop(db_conn):
    """Pruning empty memory is a no-op."""
    stats = prune_memory(db_conn)
    assert stats["total_removed"] == 0
    assert stats["total_remaining"] == 0


def test_prune_combined_policies(db_conn):
    """All policies work together correctly."""
    # Recent, high confidence — keep
    _insert_lesson(db_conn, key="good", insight="useful", confidence=0.9, days_ago=10)
    # Old but high confidence — keep
    _insert_lesson(db_conn, key="old-good", insight="still useful", confidence=0.8, days_ago=120)
    # Old and low confidence — remove
    _insert_lesson(db_conn, key="old-bad", insight="stale guess", confidence=0.3, days_ago=120)
    # Duplicate — remove older copy
    _insert_lesson(db_conn, key="dup", insight="repeated", confidence=0.6, days_ago=5)
    _insert_lesson(db_conn, key="dup", insight="repeated", confidence=0.6, days_ago=1)

    stats = prune_memory(db_conn)
    assert stats["duplicates_removed"] == 1
    assert stats["low_confidence_removed"] == 1
    assert stats["total_remaining"] == 3
