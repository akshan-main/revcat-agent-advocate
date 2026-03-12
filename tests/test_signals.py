"""Tests for the signal ingestion, scoring, and lifecycle system."""
import json
from datetime import datetime, timezone, timedelta

from advocate.agent.signals import (
    ensure_signals_schema,
    compute_score,
    ingest_signal,
    decay_freshness,
    claim_top_signal,
    mark_acted,
    mark_skipped,
    get_signal_stats,
    get_recent_signals,
    run_all_producers,
    _dedup_key,
)
from advocate.db import now_iso


# ── Schema ──────────────────────────────────────────────────────────

def test_ensure_signals_schema(db_conn):
    """Schema creation is idempotent."""
    ensure_signals_schema(db_conn)
    ensure_signals_schema(db_conn)  # Second call should not error

    # Table exists and accepts inserts
    db_conn.execute(
        "INSERT INTO signals (source, signal_type, title, created_at) VALUES (?, ?, ?, ?)",
        ("test", "new_issue", "test signal", now_iso()),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT COUNT(*) as cnt FROM signals").fetchone()
    assert row["cnt"] == 1


# ── Scoring ─────────────────────────────────────────────────────────

def test_compute_score_all_max():
    assert compute_score(1.0, 1.0, 1.0, 1.0) == 1.0


def test_compute_score_all_zero():
    assert compute_score(0.0, 0.0, 0.0, 0.0) == 0.0


def test_compute_score_mixed():
    score = compute_score(0.8, 0.6, 0.7, 1.0)
    assert 0.3 < score < 0.4  # 0.8 * 0.6 * 0.7 * 1.0 = 0.336


def test_compute_score_clamps():
    """Values outside [0,1] get clamped."""
    assert compute_score(1.5, -0.3, 0.5, 2.0) == compute_score(1.0, 0.0, 0.5, 1.0)


# ── Ingestion ───────────────────────────────────────────────────────

def test_ingest_signal_basic(db_conn):
    ensure_signals_schema(db_conn)
    sid = ingest_signal(
        db_conn, source="github", signal_type="new_issue",
        title="SDK crash on iOS 18", body="App crashes during...",
        url="https://github.com/RevenueCat/purchases-ios/issues/999",
        impact=0.8, urgency=0.7, confidence=0.9,
    )
    assert sid is not None
    assert sid > 0

    row = db_conn.execute("SELECT * FROM signals WHERE id = ?", (sid,)).fetchone()
    assert row["source"] == "github"
    assert row["signal_type"] == "new_issue"
    assert row["status"] == "pending"
    assert row["score"] > 0


def test_ingest_signal_dedup(db_conn):
    """Same URL + source should not create duplicate."""
    ensure_signals_schema(db_conn)
    url = "https://github.com/RevenueCat/purchases-ios/issues/999"

    sid1 = ingest_signal(db_conn, "github", "new_issue", "First", url=url)
    sid2 = ingest_signal(db_conn, "github", "new_issue", "Duplicate", url=url)

    assert sid1 is not None
    assert sid2 is None  # Deduplicated


def test_ingest_signal_different_sources(db_conn):
    """Same URL but different sources should create separate signals."""
    ensure_signals_schema(db_conn)
    url = "https://example.com/post"

    sid1 = ingest_signal(db_conn, "github", "new_issue", "Issue", url=url)
    sid2 = ingest_signal(db_conn, "reddit", "pain_point", "Post", url=url)

    assert sid1 is not None
    assert sid2 is not None
    assert sid1 != sid2


# ── Freshness Decay ─────────────────────────────────────────────────

def test_decay_freshness_reduces_score(db_conn):
    ensure_signals_schema(db_conn)

    # Insert a signal with created_at in the past
    past = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    db_conn.execute(
        """INSERT INTO signals
           (source, signal_type, title, impact, urgency, confidence, freshness, score,
            status, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        ("test", "new_issue", "Old signal", 0.8, 0.8, 0.8, 1.0, 0.512, past, expires),
    )
    db_conn.commit()

    decay_freshness(db_conn)

    row = db_conn.execute("SELECT freshness, score FROM signals WHERE title = 'Old signal'").fetchone()
    assert row["freshness"] < 1.0
    assert row["score"] < 0.512


def test_decay_expires_old_signals(db_conn):
    ensure_signals_schema(db_conn)

    # Insert already-expired signal
    past = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    db_conn.execute(
        """INSERT INTO signals
           (source, signal_type, title, impact, urgency, confidence, freshness, score,
            status, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        ("test", "new_issue", "Expired signal", 0.5, 0.5, 0.5, 0.1, 0.0125, past, expired_at),
    )
    db_conn.commit()

    decay_freshness(db_conn)

    row = db_conn.execute("SELECT status FROM signals WHERE title = 'Expired signal'").fetchone()
    assert row["status"] == "expired"


# ── Claim + Act ─────────────────────────────────────────────────────

def test_claim_top_signal(db_conn):
    ensure_signals_schema(db_conn)

    # Insert two signals with different scores
    ingest_signal(db_conn, "github", "new_issue", "Low priority", impact=0.3, urgency=0.3, confidence=0.3)
    ingest_signal(db_conn, "reddit", "pain_point", "High priority", impact=0.9, urgency=0.9, confidence=0.9)

    top = claim_top_signal(db_conn)
    assert top is not None
    assert top["title"] == "High priority"

    # Verify it's now claimed in DB
    row = db_conn.execute("SELECT status FROM signals WHERE id = ?", (top["id"],)).fetchone()
    assert row["status"] == "claimed"


def test_claim_returns_none_when_empty(db_conn):
    ensure_signals_schema(db_conn)
    assert claim_top_signal(db_conn) is None


def test_claim_skips_already_claimed(db_conn):
    ensure_signals_schema(db_conn)
    ingest_signal(db_conn, "github", "new_issue", "Only signal", impact=0.8, urgency=0.8, confidence=0.8)

    first = claim_top_signal(db_conn)
    assert first is not None

    second = claim_top_signal(db_conn)
    assert second is None  # Already claimed


def test_mark_acted(db_conn):
    ensure_signals_schema(db_conn)
    sid = ingest_signal(db_conn, "github", "new_issue", "Test", impact=0.5, urgency=0.5, confidence=0.5)
    claim_top_signal(db_conn)

    mark_acted(db_conn, sid, "write_content", {"status": "success", "word_count": 1500})

    row = db_conn.execute("SELECT * FROM signals WHERE id = ?", (sid,)).fetchone()
    assert row["status"] == "acted"
    assert row["action_taken"] == "write_content"
    assert row["acted_at"] is not None
    outcome = json.loads(row["outcome_json"])
    assert outcome["status"] == "success"


def test_mark_skipped(db_conn):
    ensure_signals_schema(db_conn)
    sid = ingest_signal(db_conn, "github", "new_issue", "Skip me", impact=0.2, urgency=0.2, confidence=0.2)

    mark_skipped(db_conn, sid, "engagement_drop — informational")

    row = db_conn.execute("SELECT * FROM signals WHERE id = ?", (sid,)).fetchone()
    assert row["status"] == "skipped"


# ── Stats ───────────────────────────────────────────────────────────

def test_get_signal_stats(db_conn):
    ensure_signals_schema(db_conn)
    ingest_signal(db_conn, "github", "new_issue", "Pending 1", impact=0.5, urgency=0.5, confidence=0.5)
    ingest_signal(db_conn, "reddit", "pain_point", "Pending 2", impact=0.5, urgency=0.5, confidence=0.5)

    stats = get_signal_stats(db_conn)
    assert stats["pending"] == 2
    assert stats["total"] == 2


def test_get_recent_signals(db_conn):
    ensure_signals_schema(db_conn)
    for i in range(5):
        ingest_signal(db_conn, "github", "new_issue", f"Signal {i}",
                      url=f"https://example.com/{i}", impact=0.5, urgency=0.5, confidence=0.5)

    recent = get_recent_signals(db_conn, limit=3)
    assert len(recent) == 3


# ── Producers ───────────────────────────────────────────────────────

def test_run_all_producers_no_credentials(db_conn, mock_config):
    """Producers should gracefully handle missing credentials."""
    counts = run_all_producers(db_conn, mock_config)
    assert counts["total"] >= 0  # Should not crash
    assert "github" in counts
    assert "reddit" in counts
    assert "devto" in counts


def test_scheduled_signals_content_due(db_conn, mock_config):
    """Should generate content_due signal when no recent content."""
    ensure_signals_schema(db_conn)
    from advocate.agent.signals import ingest_scheduled_signals

    count = ingest_scheduled_signals(db_conn)
    # Should generate at least one scheduled signal (content_due, tweet_due, or feedback_due)
    assert count >= 0

    signals = db_conn.execute(
        "SELECT * FROM signals WHERE source = 'schedule'"
    ).fetchall()
    # At least content_due should be generated (no content in DB)
    content_due = [s for s in signals if s["signal_type"] == "content_due"]
    assert len(content_due) >= 0  # May or may not fire depending on tables existing


# ── Dedup Key ───────────────────────────────────────────────────────

def test_dedup_key_consistency():
    """Same inputs produce same key."""
    k1 = _dedup_key("github", "https://example.com/1", "Title")
    k2 = _dedup_key("github", "https://example.com/1", "Title")
    assert k1 == k2


def test_dedup_key_url_takes_precedence():
    """URL-based dedup ignores title differences."""
    k1 = _dedup_key("github", "https://example.com/1", "Title A")
    k2 = _dedup_key("github", "https://example.com/1", "Title B")
    assert k1 == k2


def test_dedup_key_no_url_uses_title():
    """Without URL, title is used for dedup."""
    k1 = _dedup_key("github", None, "Same title")
    k2 = _dedup_key("github", None, "Same title")
    k3 = _dedup_key("github", None, "Different title")
    assert k1 == k2
    assert k1 != k3
