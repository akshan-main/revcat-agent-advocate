"""Tests for Thompson sampling bandit topic selection."""
from advocate.agent.bandit import (
    ensure_bandit_schema,
    classify_topic,
    pull_arm,
    update_reward,
    compute_reward,
    sync_rewards_from_devto,
    get_arm_stats,
    get_topic_for_category,
    ARM_CATEGORIES,
)


# ── Schema ──────────────────────────────────────────────────────────

def test_ensure_bandit_schema(db_conn):
    ensure_bandit_schema(db_conn)

    arms = db_conn.execute("SELECT COUNT(*) as cnt FROM bandit_arms").fetchone()
    assert arms["cnt"] == len(ARM_CATEGORIES)


def test_schema_is_idempotent(db_conn):
    ensure_bandit_schema(db_conn)
    ensure_bandit_schema(db_conn)

    arms = db_conn.execute("SELECT COUNT(*) as cnt FROM bandit_arms").fetchone()
    assert arms["cnt"] == len(ARM_CATEGORIES)


# ── Classification ──────────────────────────────────────────────────

def test_classify_sdk_topic():
    assert classify_topic("Getting Started with RevenueCat SDK Setup") == "sdk_integration"


def test_classify_billing_topic():
    assert classify_topic("Understanding Subscription Lifecycle and Renewals") == "billing_lifecycle"


def test_classify_charts_topic():
    assert classify_topic("Building an MRR Dashboard with Charts API") == "analytics_charts"


def test_classify_migration_topic():
    assert classify_topic("Migrating from StoreKit to RevenueCat") == "migration_guide"


def test_classify_paywall_topic():
    assert classify_topic("A/B Testing Paywalls and Offerings") == "paywall_optimization"


def test_classify_mcp_topic():
    assert classify_topic("Using RevenueCat MCP Server for Agent Integration") == "agentic_ai"


def test_classify_unknown_defaults_to_agentic():
    assert classify_topic("Some completely unrelated topic about cooking") == "agentic_ai"


# ── Thompson Sampling ──────────────────────────────────────────────

def test_pull_arm_returns_valid_category(db_conn):
    ensure_bandit_schema(db_conn)
    arm = pull_arm(db_conn)
    assert arm in ARM_CATEGORIES


def test_pull_arm_updates_pull_count(db_conn):
    ensure_bandit_schema(db_conn)
    arm = pull_arm(db_conn)

    row = db_conn.execute(
        "SELECT total_pulls FROM bandit_arms WHERE arm_name = ?", (arm,)
    ).fetchone()
    assert row["total_pulls"] == 1


def test_pull_arm_multiple_times(db_conn):
    """Multiple pulls should work and not always return the same arm."""
    ensure_bandit_schema(db_conn)
    arms_seen = set()
    for _ in range(50):
        arms_seen.add(pull_arm(db_conn))

    # With uniform priors, should see at least a few different arms
    assert len(arms_seen) >= 2


# ── Reward Updates ──────────────────────────────────────────────────

def test_update_reward(db_conn):
    ensure_bandit_schema(db_conn)

    # Get initial alpha/beta
    row = db_conn.execute(
        "SELECT alpha, beta FROM bandit_arms WHERE arm_name = 'analytics_charts'"
    ).fetchone()
    initial_alpha = row["alpha"]

    update_reward(db_conn, "analytics_charts", 0.8)

    row = db_conn.execute(
        "SELECT alpha, beta, total_reward FROM bandit_arms WHERE arm_name = 'analytics_charts'"
    ).fetchone()
    assert row["alpha"] == initial_alpha + 0.8
    assert row["total_reward"] == 0.8


def test_update_reward_clamps(db_conn):
    ensure_bandit_schema(db_conn)

    row_before = db_conn.execute(
        "SELECT alpha FROM bandit_arms WHERE arm_name = 'sdk_integration'"
    ).fetchone()

    update_reward(db_conn, "sdk_integration", 1.5)  # Should clamp to 1.0

    row_after = db_conn.execute(
        "SELECT alpha FROM bandit_arms WHERE arm_name = 'sdk_integration'"
    ).fetchone()
    assert row_after["alpha"] == row_before["alpha"] + 1.0


def test_reward_shifts_distribution(db_conn):
    """Arms with higher rewards should have higher expected values."""
    ensure_bandit_schema(db_conn)

    # Give one arm high reward, another low
    for _ in range(5):
        update_reward(db_conn, "analytics_charts", 0.9)
        update_reward(db_conn, "troubleshooting", 0.1)

    stats = get_arm_stats(db_conn)
    charts_ev = next(s["expected_value"] for s in stats if s["arm_name"] == "analytics_charts")
    trouble_ev = next(s["expected_value"] for s in stats if s["arm_name"] == "troubleshooting")

    assert charts_ev > trouble_ev


# ── Compute Reward ──────────────────────────────────────────────────

def test_compute_reward_views():
    assert compute_reward(500, 0, 0) == 1.0
    assert compute_reward(250, 0, 0) == 0.5


def test_compute_reward_reactions():
    assert compute_reward(0, 20, 0) == 1.0
    assert compute_reward(0, 10, 0) == 0.5


def test_compute_reward_comments():
    assert compute_reward(0, 0, 10) == 1.0


def test_compute_reward_takes_max():
    """Reward uses max of individual scores."""
    assert compute_reward(500, 0, 0) == compute_reward(0, 20, 0) == 1.0


def test_compute_reward_zero():
    assert compute_reward(0, 0, 0) == 0.0


# ── Arm Stats ───────────────────────────────────────────────────────

def test_get_arm_stats(db_conn):
    ensure_bandit_schema(db_conn)
    stats = get_arm_stats(db_conn)

    assert len(stats) == len(ARM_CATEGORIES)
    for stat in stats:
        assert "arm_name" in stat
        assert "expected_value" in stat
        assert "description" in stat
        assert 0 <= stat["expected_value"] <= 1


# ── Topic Suggestions ──────────────────────────────────────────────

def test_get_topic_for_category():
    for arm_name in ARM_CATEGORIES:
        topics = get_topic_for_category(arm_name)
        assert len(topics) >= 1
        assert all(isinstance(t, str) for t in topics)


def test_get_topic_for_unknown_category():
    topics = get_topic_for_category("nonexistent_category")
    assert len(topics) >= 1


# ── Dev.to Sync ─────────────────────────────────────────────────────

def test_sync_rewards_no_devto(db_conn, mock_config):
    """Should return 0 when no Dev.to key."""
    ensure_bandit_schema(db_conn)
    assert sync_rewards_from_devto(db_conn, mock_config) == 0
