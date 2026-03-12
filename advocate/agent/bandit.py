"""Thompson sampling bandit for topic selection.

Instead of picking topics randomly or from a fixed list, the agent uses a
multi-armed bandit to balance exploration (new categories) and exploitation
(categories that perform well on Dev.to). Reward signal comes from Dev.to
engagement metrics (views, reactions, comments).

Each "arm" is a topic category. The bandit maintains Beta(alpha, beta)
distributions and samples to choose which category to write about next.
"""
import random

from ..config import Config
from ..db import DBConnection, now_iso


# ── Schema ──────────────────────────────────────────────────────────

BANDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS bandit_arms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arm_name TEXT UNIQUE NOT NULL,
    alpha REAL NOT NULL DEFAULT 1.0,
    beta REAL NOT NULL DEFAULT 1.0,
    total_pulls INTEGER NOT NULL DEFAULT 0,
    total_reward REAL NOT NULL DEFAULT 0.0,
    last_pulled_at TEXT,
    created_at TEXT NOT NULL
);
"""

# Topic categories (arms). Each maps to content themes.
ARM_CATEGORIES = {
    "sdk_integration": {
        "keywords": ["sdk", "install", "configure", "setup", "initialize", "purchases-ios", "purchases-android"],
        "description": "SDK installation, configuration, and platform-specific integration",
    },
    "billing_lifecycle": {
        "keywords": ["subscription", "billing", "lifecycle", "renewal", "cancel", "expire", "grace period", "webhook"],
        "description": "Subscription lifecycle events, billing, renewals, cancellations",
    },
    "migration_guide": {
        "keywords": ["migrate", "migration", "storekit", "billing client", "stripe", "adapty", "qonversion", "switch"],
        "description": "Migrating from other platforms or native billing to RevenueCat",
    },
    "paywall_optimization": {
        "keywords": ["paywall", "offering", "package", "conversion", "trial", "paywall ui", "remote config"],
        "description": "Paywalls, offerings, A/B testing, conversion optimization",
    },
    "analytics_charts": {
        "keywords": ["charts", "analytics", "mrr", "arr", "churn", "ltv", "revenue", "metrics", "dashboard"],
        "description": "Charts API, analytics, revenue metrics, dashboards",
    },
    "cross_platform": {
        "keywords": ["flutter", "react native", "unity", "kotlin multiplatform", "cross-platform", "kmp"],
        "description": "Cross-platform development with RevenueCat SDKs",
    },
    "storekit_play_billing": {
        "keywords": ["storekit 2", "play billing", "receipt", "validation", "server-side", "app store"],
        "description": "Native store APIs, receipt validation, server-side verification",
    },
    "agentic_ai": {
        "keywords": ["mcp", "agent", "agentic", "llm", "ai", "automation", "tool use"],
        "description": "MCP server, agentic AI integration, LLM-powered monetization",
    },
    "pricing_strategy": {
        "keywords": ["pricing", "tier", "freemium", "premium", "monetization", "strategy", "offer code"],
        "description": "Pricing strategies, monetization models, offer codes",
    },
    "troubleshooting": {
        "keywords": ["error", "debug", "fix", "issue", "crash", "not working", "troubleshoot", "restore"],
        "description": "Common issues, debugging, error handling, restore purchases",
    },
}


def ensure_bandit_schema(conn: DBConnection):
    """Create bandit_arms table and seed arms with uniform priors."""
    for stmt in BANDIT_SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception:
                pass
    conn.commit()

    # Seed arms that don't exist yet
    now = now_iso()
    for arm_name in ARM_CATEGORIES:
        existing = conn.execute(
            "SELECT id FROM bandit_arms WHERE arm_name = ?", (arm_name,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO bandit_arms (arm_name, alpha, beta, total_pulls, total_reward, created_at) "
                "VALUES (?, 1.0, 1.0, 0, 0.0, ?)",
                (arm_name, now),
            )
    conn.commit()


def classify_topic(title: str, body: str = "") -> str:
    """Classify a content piece into a bandit arm category using keyword matching.

    No LLM needed — just keyword frequency against each arm's keyword list.
    Returns the best-matching arm name, or 'agentic_ai' as default.
    """
    text = f"{title} {body}".lower()
    scores = {}

    for arm_name, arm_info in ARM_CATEGORIES.items():
        score = sum(1 for kw in arm_info["keywords"] if kw.lower() in text)
        if score > 0:
            scores[arm_name] = score

    if not scores:
        return "agentic_ai"  # Default arm

    return max(scores, key=scores.get)


def pull_arm(conn: DBConnection) -> str:
    """Thompson sampling: sample from Beta(alpha, beta) for each arm, return the winner.

    Updates pull count and last_pulled_at for the selected arm.
    """
    ensure_bandit_schema(conn)

    arms = conn.execute(
        "SELECT arm_name, alpha, beta, total_pulls FROM bandit_arms"
    ).fetchall()

    if not arms:
        return "agentic_ai"

    # Thompson sampling: draw from Beta distribution for each arm
    samples = {}
    for arm in arms:
        alpha = max(0.01, arm["alpha"])
        beta_val = max(0.01, arm["beta"])
        samples[arm["arm_name"]] = random.betavariate(alpha, beta_val)

    winner = max(samples, key=samples.get)

    # Update the winner
    conn.execute(
        "UPDATE bandit_arms SET total_pulls = total_pulls + 1, last_pulled_at = ? WHERE arm_name = ?",
        (now_iso(), winner),
    )
    conn.commit()

    return winner


def update_reward(conn: DBConnection, arm_name: str, reward: float):
    """Update arm with observed reward. Reward in [0, 1].

    Uses Bayesian update: alpha += reward, beta += (1 - reward).
    """
    reward = max(0.0, min(1.0, reward))

    conn.execute(
        "UPDATE bandit_arms SET alpha = alpha + ?, beta = beta + ?, total_reward = total_reward + ? "
        "WHERE arm_name = ?",
        (reward, 1.0 - reward, reward, arm_name),
    )
    conn.commit()


def compute_reward(views: int, reactions: int, comments: int) -> float:
    """Compute normalized reward from Dev.to engagement.

    Scale: 500 views OR 20 reactions OR 10 comments = reward of 1.0.
    Uses max of individual normalized scores.
    """
    view_score = min(1.0, views / 500)
    reaction_score = min(1.0, reactions / 20)
    comment_score = min(1.0, comments / 10)
    return max(view_score, reaction_score, comment_score)


def sync_rewards_from_devto(conn: DBConnection, config: Config) -> int:
    """Sync Dev.to engagement data back to bandit arms.

    Queries content_pieces with devto_article_id, classifies each into
    an arm, and updates rewards based on engagement.

    Returns number of arms updated.
    """
    if not config.has_devto:
        return 0

    ensure_bandit_schema(conn)

    # Get all published content with Dev.to stats
    articles = conn.execute(
        "SELECT title, body_md, devto_views, devto_reactions, devto_comments "
        "FROM content_pieces WHERE devto_article_id IS NOT NULL"
    ).fetchall()

    # Aggregate rewards per arm
    arm_rewards: dict[str, list[float]] = {}
    for article in articles:
        arm = classify_topic(article["title"], article.get("body_md", "") or "")
        views = article.get("devto_views") or 0
        reactions = article.get("devto_reactions") or 0
        comments = article.get("devto_comments") or 0

        if views > 0 or reactions > 0:
            reward = compute_reward(views, reactions, comments)
            arm_rewards.setdefault(arm, []).append(reward)

    # Reset ALL arms to uniform priors before re-applying, so we don't
    # inflate rewards by re-counting the same historical stats every cycle.
    conn.execute(
        "UPDATE bandit_arms SET alpha = 1.0, beta = 1.0, total_reward = 0.0"
    )

    # Apply accumulated rewards from scratch
    updated = 0
    for arm_name, rewards in arm_rewards.items():
        for reward in rewards:
            update_reward(conn, arm_name, reward)
        updated += 1

    conn.commit()
    return updated


def get_arm_stats(conn: DBConnection) -> list[dict]:
    """Get all arms with their stats for display."""
    ensure_bandit_schema(conn)
    arms = conn.execute(
        "SELECT arm_name, alpha, beta, total_pulls, total_reward, last_pulled_at, created_at "
        "FROM bandit_arms ORDER BY alpha/(alpha+beta) DESC"
    ).fetchall()
    result = []
    for arm in arms:
        alpha = arm["alpha"]
        beta_val = arm["beta"]
        result.append({
            "arm_name": arm["arm_name"],
            "alpha": alpha,
            "beta": beta_val,
            "expected_value": alpha / (alpha + beta_val) if (alpha + beta_val) > 0 else 0.5,
            "total_pulls": arm["total_pulls"],
            "total_reward": arm["total_reward"],
            "last_pulled_at": arm["last_pulled_at"],
            "description": ARM_CATEGORIES.get(arm["arm_name"], {}).get("description", ""),
        })
    return result


def get_topic_for_category(arm_name: str) -> list[str]:
    """Get suggested topic prompts for a given arm category."""
    topics = {
        "sdk_integration": [
            "Getting Started with RevenueCat SDK: Platform-Specific Setup Guide",
            "Advanced RevenueCat SDK Configuration for Production Apps",
        ],
        "billing_lifecycle": [
            "Understanding Subscription Lifecycle Events in RevenueCat",
            "Handling Grace Periods and Billing Retries with RevenueCat",
        ],
        "migration_guide": [
            "Migrating from StoreKit to RevenueCat: A Complete Guide",
            "Switching from Stripe Billing to RevenueCat for Mobile Apps",
        ],
        "paywall_optimization": [
            "A/B Testing Paywalls with RevenueCat: Data-Driven Conversion",
            "Building Remote-Configurable Paywalls with RevenueCat Offerings",
        ],
        "analytics_charts": [
            "Using RevenueCat Charts API for Subscription Analytics",
            "Building an MRR Dashboard with RevenueCat Charts",
        ],
        "cross_platform": [
            "RevenueCat Flutter Integration: Subscriptions Across iOS and Android",
            "React Native In-App Purchases with RevenueCat",
        ],
        "storekit_play_billing": [
            "StoreKit 2 and RevenueCat: Modern Apple Subscription Handling",
            "Server-Side Receipt Validation with RevenueCat",
        ],
        "agentic_ai": [
            "Building Agent-Native Monetization with RevenueCat MCP Server",
            "LLM-Powered Subscription Management via RevenueCat Tools",
        ],
        "pricing_strategy": [
            "Subscription Pricing Strategies: Lessons from RevenueCat Data",
            "Optimizing Trial-to-Paid Conversion with RevenueCat",
        ],
        "troubleshooting": [
            "Debugging Common RevenueCat Integration Issues",
            "RevenueCat Error Handling: A Developer's Guide",
        ],
    }
    return topics.get(arm_name, ["RevenueCat Developer Guide"])
