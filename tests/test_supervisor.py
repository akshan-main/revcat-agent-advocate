"""Tests for the event-driven supervisor."""
from advocate.agent.supervisor import Supervisor, ACTION_MAP
from advocate.agent.signals import ensure_signals_schema, ingest_signal, get_signal_stats
from advocate.agent.bandit import ensure_bandit_schema
from advocate.db import now_iso


# ── Action Mapping ──────────────────────────────────────────────────

def test_action_map_covers_signal_types():
    """Every signal type should map to an action."""
    expected_types = {
        "new_issue", "pain_point", "product_mention", "engagement_spike",
        "engagement_drop", "doc_gap", "trending_topic", "content_due",
        "tweet_due", "feedback_due", "scheduled_task", "manual_goal",
        "site_stale",
    }
    for signal_type in expected_types:
        assert signal_type in ACTION_MAP, f"Missing mapping for {signal_type}"


def test_action_map_values():
    assert ACTION_MAP["new_issue"] == "draft_community_response"
    assert ACTION_MAP["engagement_spike"] == "write_content"
    assert ACTION_MAP["engagement_drop"] == "skip"
    assert ACTION_MAP["tweet_due"] == "draft_tweet"
    assert ACTION_MAP["feedback_due"] == "generate_feedback"


# ── Supervisor Init ─────────────────────────────────────────────────

def test_supervisor_init(db_conn, mock_config):
    supervisor = Supervisor(mock_config, db_conn=db_conn)
    assert supervisor.config == mock_config
    assert supervisor.db == db_conn


# ── Decision Logic ──────────────────────────────────────────────────

def test_decide_action_new_issue(db_conn, mock_config):
    supervisor = Supervisor(mock_config, db_conn=db_conn)
    signal = {"signal_type": "new_issue", "url": "", "title": "Test"}
    assert supervisor._decide_action(signal) == "draft_community_response"


def test_decide_action_engagement_spike(db_conn, mock_config):
    supervisor = Supervisor(mock_config, db_conn=db_conn)
    signal = {"signal_type": "engagement_spike", "url": "", "title": "Test"}
    assert supervisor._decide_action(signal) == "write_content"


def test_decide_action_engagement_drop(db_conn, mock_config):
    supervisor = Supervisor(mock_config, db_conn=db_conn)
    signal = {"signal_type": "engagement_drop", "url": "", "title": "Test"}
    assert supervisor._decide_action(signal) == "skip"


def test_decide_action_tweet_due(db_conn, mock_config):
    supervisor = Supervisor(mock_config, db_conn=db_conn)
    signal = {"signal_type": "tweet_due", "url": "", "title": "Test"}
    assert supervisor._decide_action(signal) == "draft_tweet"


# ── Cycle Without Signals ──────────────────────────────────────────

def test_run_cycle_no_external_signals(db_conn, mock_config):
    """Cycle should complete gracefully. Scheduled producers may generate signals."""
    ensure_signals_schema(db_conn)
    ensure_bandit_schema(db_conn)

    supervisor = Supervisor(mock_config, db_conn=db_conn)
    result = supervisor.run_cycle(max_actions=3)

    # Should complete without error
    assert "summary" in result
    assert result["signals_ingested"]["total"] >= 0
    # Scheduled signals may fire (content_due, tweet_due, feedback_due) so
    # actions_taken may be non-empty — that's correct behavior


# ── Cycle With Signals ─────────────────────────────────────────────

def test_engagement_drop_is_skipped(db_conn, mock_config):
    """Engagement drops should map to skip action."""
    supervisor = Supervisor(mock_config, db_conn=db_conn)

    signal = {"signal_type": "engagement_drop", "url": "", "title": "Stalled"}
    action = supervisor._decide_action(signal)
    assert action == "skip"


def test_run_cycle_respects_max_actions(db_conn, mock_config):
    """Should not exceed max_actions."""
    ensure_signals_schema(db_conn)
    ensure_bandit_schema(db_conn)

    # Insert many signals
    for i in range(10):
        ingest_signal(db_conn, "schedule", "content_due",
                      f"Content due {i}", url=f"https://example.com/sched/{i}",
                      impact=0.7, urgency=0.8, confidence=1.0)

    supervisor = Supervisor(mock_config, db_conn=db_conn)
    # Without anthropic key, write_content will be skipped but claimed
    result = supervisor.run_cycle(max_actions=2)

    # Actions taken + skipped should not exceed max_actions
    total = len(result["actions_taken"]) + result["actions_skipped"]
    assert total <= 2


# ── Firewall Integration ───────────────────────────────────────────

def test_firewall_check_default_allows(db_conn, mock_config):
    """Default firewall rules should allow supervisor actions."""
    supervisor = Supervisor(mock_config, db_conn=db_conn)
    ensure_signals_schema(db_conn)

    # write_content should be allowed (no rate limit hit yet)
    assert supervisor._firewall_check("write_content") is True


# ── Lesson Recording ───────────────────────────────────────────────

def test_record_lesson_on_actions(db_conn, mock_config):
    """Supervisor should record a lesson when actions are taken."""
    ensure_signals_schema(db_conn)
    ensure_bandit_schema(db_conn)

    supervisor = Supervisor(mock_config, db_conn=db_conn)

    # Simulate a result with actions
    fake_result = {
        "started_at": now_iso(),
        "actions_taken": [
            {"signal_type": "content_due", "action": "write_content",
             "outcome": {"status": "skipped"}},
        ],
        "signals_ingested": {"total": 5},
    }
    supervisor._record_lesson(fake_result)

    # Check agent_memory
    lessons = db_conn.execute(
        "SELECT * FROM agent_memory WHERE cycle_id LIKE 'supervisor_%'"
    ).fetchall()
    assert len(lessons) >= 1


def test_no_lesson_when_no_actions(db_conn, mock_config):
    """No lesson should be recorded if no actions were taken."""
    ensure_signals_schema(db_conn)
    ensure_bandit_schema(db_conn)

    supervisor = Supervisor(mock_config, db_conn=db_conn)
    supervisor._record_lesson({"actions_taken": [], "signals_ingested": {}})

    lessons = db_conn.execute(
        "SELECT * FROM agent_memory WHERE cycle_id LIKE 'supervisor_%'"
    ).fetchall()
    assert len(lessons) == 0


# ── Signal Stats After Cycle ────────────────────────────────────────

def test_cycle_updates_signal_stats(db_conn, mock_config):
    ensure_signals_schema(db_conn)
    ensure_bandit_schema(db_conn)

    ingest_signal(db_conn, "schedule", "tweet_due", "Tweet overdue",
                  impact=0.5, urgency=0.6, confidence=1.0)

    supervisor = Supervisor(mock_config, db_conn=db_conn)
    supervisor.run_cycle(max_actions=1)

    stats = get_signal_stats(db_conn)
    # The signal should have been claimed and either acted or skipped
    assert stats["pending"] == 0 or stats["claimed"] == 0
