"""Event-driven signal ingestion, scoring, and lifecycle management.

Signals are normalized events from multiple sources (GitHub issues, Reddit posts,
Dev.to engagement changes, doc updates, scheduled tasks). Each signal is scored by
impact * urgency * confidence * freshness, and the supervisor claims the top-scoring
signal to decide its next action.

The signals table is managed here (not in db.py SCHEMA) following the same pattern
as distribution/pipeline.py — self-contained schema with idempotent creation.
"""
import hashlib
import json
from datetime import datetime, timezone, timedelta

from ..config import Config
from ..db import DBConnection, now_iso


# ── Schema ──────────────────────────────────────────────────────────

SIGNALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    url TEXT,
    metadata_json TEXT,
    impact REAL NOT NULL DEFAULT 0.5,
    urgency REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.5,
    freshness REAL NOT NULL DEFAULT 1.0,
    score REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'pending',
    claimed_by TEXT,
    action_taken TEXT,
    outcome_json TEXT,
    created_at TEXT NOT NULL,
    acted_at TEXT,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);
"""

VALID_SOURCES = {
    "github", "reddit", "devto_stats", "doc_change",
    "schedule", "manual", "devto_trending", "twitter",
}

VALID_SIGNAL_TYPES = {
    "pain_point", "product_mention", "engagement_spike", "engagement_drop",
    "doc_gap", "new_issue", "trending_topic", "scheduled_task", "manual_goal",
    "content_due", "site_stale", "feedback_due", "tweet_due",
}


def ensure_signals_schema(conn: DBConnection):
    """Create signals table if it doesn't exist. Idempotent."""
    for stmt in SIGNALS_SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception:
                pass
    conn.commit()


# ── Scoring ─────────────────────────────────────────────────────────

def compute_score(impact: float, urgency: float, confidence: float, freshness: float) -> float:
    """Score = impact * urgency * confidence * freshness. All clamped to [0, 1]."""
    return (
        max(0.0, min(1.0, impact))
        * max(0.0, min(1.0, urgency))
        * max(0.0, min(1.0, confidence))
        * max(0.0, min(1.0, freshness))
    )


# ── Signal Lifecycle ────────────────────────────────────────────────

def _dedup_key(source: str, url: str | None, title: str) -> str:
    """Generate a deduplication key from source + url or title hash."""
    if url:
        return hashlib.sha256(f"{source}:{url}".encode()).hexdigest()[:32]
    return hashlib.sha256(f"{source}:{title}".encode()).hexdigest()[:32]


def ingest_signal(
    conn: DBConnection,
    source: str,
    signal_type: str,
    title: str,
    body: str = "",
    url: str | None = None,
    metadata: dict | None = None,
    impact: float = 0.5,
    urgency: float = 0.5,
    confidence: float = 0.5,
    ttl_hours: int = 48,
) -> int | None:
    """Ingest a single signal. Deduplicates by (source, url) or (source, title_hash).

    Returns signal ID or None if duplicate.
    """
    dedup = _dedup_key(source, url, title)

    existing = conn.execute(
        "SELECT id FROM signals WHERE url = ? AND source = ?",
        (url or dedup, source),
    ).fetchone()
    if existing:
        return None

    now = now_iso()
    expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
    score = compute_score(impact, urgency, confidence, 1.0)

    cursor = conn.execute(
        """INSERT INTO signals
           (source, signal_type, title, body, url, metadata_json,
            impact, urgency, confidence, freshness, score,
            status, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (
            source, signal_type, title, body, url or dedup,
            json.dumps(metadata or {}),
            impact, urgency, confidence, 1.0, score,
            now, expires,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def decay_freshness(conn: DBConnection):
    """Decay freshness of all pending signals based on age. Expire old ones."""
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    # Expire signals past their TTL
    conn.execute(
        "UPDATE signals SET status = 'expired' WHERE status = 'pending' AND expires_at < ?",
        (now_str,),
    )

    # Decay freshness for remaining pending signals
    pending = conn.execute(
        "SELECT id, created_at, expires_at, impact, urgency, confidence FROM signals WHERE status = 'pending'"
    ).fetchall()

    for sig in pending:
        created = datetime.fromisoformat(sig["created_at"])
        expires = datetime.fromisoformat(sig["expires_at"])
        ttl_hours = max(1, (expires - created).total_seconds() / 3600)
        age_hours = (now - created).total_seconds() / 3600
        freshness = max(0.05, 1.0 - age_hours / ttl_hours)
        score = compute_score(sig["impact"], sig["urgency"], sig["confidence"], freshness)

        conn.execute(
            "UPDATE signals SET freshness = ?, score = ? WHERE id = ?",
            (freshness, score, sig["id"]),
        )

    conn.commit()


def claim_top_signal(conn: DBConnection, claimed_by: str = "supervisor") -> dict | None:
    """Atomically claim the highest-scoring pending signal. Returns it or None.

    Uses compare-and-swap: UPDATE with WHERE status='pending' ensures that
    concurrent supervisors cannot claim the same signal.
    """
    top = conn.execute(
        "SELECT * FROM signals WHERE status = 'pending' ORDER BY score DESC LIMIT 1"
    ).fetchone()

    if not top:
        return None

    # CAS: only claim if status is still 'pending' (prevents double-claim)
    conn.execute(
        "UPDATE signals SET status = 'claimed', claimed_by = ? "
        "WHERE id = ? AND status = 'pending'",
        (claimed_by, top["id"]),
    )
    conn.commit()

    # Verify we actually claimed it (another supervisor may have won the race)
    row = conn.execute(
        "SELECT * FROM signals WHERE id = ? AND claimed_by = ?",
        (top["id"], claimed_by),
    ).fetchone()

    if not row:
        return None  # Lost the race — caller should retry

    return dict(row)


def mark_acted(conn: DBConnection, signal_id: int, action_taken: str, outcome: dict):
    """Mark a signal as acted upon with outcome details."""
    conn.execute(
        "UPDATE signals SET status = 'acted', action_taken = ?, outcome_json = ?, acted_at = ? WHERE id = ?",
        (action_taken, json.dumps(outcome), now_iso(), signal_id),
    )
    conn.commit()


def mark_skipped(conn: DBConnection, signal_id: int, reason: str):
    """Mark a signal as skipped."""
    conn.execute(
        "UPDATE signals SET status = 'skipped', outcome_json = ? WHERE id = ?",
        (json.dumps({"reason": reason}), signal_id),
    )
    conn.commit()


def get_signal_stats(conn: DBConnection) -> dict:
    """Get signal counts by status for reporting."""
    stats = {}
    for status in ("pending", "claimed", "acted", "skipped", "expired"):
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM signals WHERE status = ?", (status,)
        ).fetchone()
        stats[status] = row["cnt"] if row else 0
    stats["total"] = sum(stats.values())
    return stats


def get_recent_signals(conn: DBConnection, limit: int = 20) -> list[dict]:
    """Get recent signals for display."""
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ── Signal Producers ────────────────────────────────────────────────
# Each producer scans an external source and calls ingest_signal().

def ingest_github_signals(conn: DBConnection, config: Config, since_hours: int = 72) -> int:
    """Scan GitHub repos for issues and ingest as signals. Returns count ingested."""
    if not config.github_token:
        return 0

    from ..social.github_responder import GitHubResponder

    responder = GitHubResponder(config)
    count = 0

    try:
        issues = responder.find_issues(since_hours=since_hours, limit=15)
    except Exception:
        return 0

    for issue in issues:
        # Skip agent-task issues — handled by separate workflow
        labels = issue.get("labels", [])
        if "agent-task" in labels:
            continue

        # Score based on labels and engagement
        impact = 0.7
        if any(lbl in ("bug", "crash", "critical") for lbl in labels):
            impact = 0.9
        elif any(lbl in ("question", "help wanted") for lbl in labels):
            impact = 0.6

        # Urgency from age (newer = more urgent)
        try:
            created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            urgency = max(0.2, 1.0 - age_hours / (since_hours * 2))
        except Exception:
            urgency = 0.5

        signal_type = "pain_point" if "bug" in labels else "new_issue"

        result = ingest_signal(
            conn,
            source="github",
            signal_type=signal_type,
            title=issue["title"],
            body=issue.get("body", "")[:500],
            url=issue["url"],
            metadata={"repo": issue["repo"], "number": issue["number"], "labels": labels, "user": issue.get("user", "")},
            impact=impact,
            urgency=urgency,
            confidence=0.8,
            ttl_hours=72,
        )
        if result:
            count += 1

    return count


def ingest_task_issues(conn: DBConnection, config: Config) -> int:
    """Scan this repo for issues labeled 'agent-task' and ingest as manual_goal signals."""
    if not config.github_token or not config.github_repo:
        return 0

    import requests
    count = 0

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{config.github_repo}/issues",
            params={"state": "open", "labels": "agent-task", "per_page": 10, "sort": "created"},
            headers={
                "Authorization": f"token {config.github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return 0

        for issue in resp.json():
            labels = [lbl["name"] for lbl in issue.get("labels", [])]
            result = ingest_signal(
                conn,
                source="github",
                signal_type="manual_goal",
                title=issue["title"],
                body=issue.get("body", "")[:1000],
                url=issue["html_url"],
                metadata={
                    "repo": config.github_repo,
                    "number": issue["number"],
                    "labels": labels,
                    "user": issue.get("user", {}).get("login", ""),
                },
                impact=0.9,
                urgency=0.9,
                confidence=1.0,
                ttl_hours=168,
            )
            if result:
                count += 1
    except Exception:
        pass

    return count


def ingest_reddit_signals(conn: DBConnection, config: Config, since_hours: int = 72) -> int:
    """Scan Reddit for actionable subscription/IAP pain points.

    Quality gates — a post must meet ALL of:
    1. Minimum engagement: score >= 3 OR num_comments >= 2
    2. Actionable: contains a question mark, or matches pain-point keywords
    3. Not just a passing mention of RevenueCat

    This prevents noise from low-quality or irrelevant posts.
    """
    from ..social.reddit import RedditClient

    client = RedditClient(config)
    count = 0

    try:
        posts = client.find_posts(since_hours=since_hours, limit=20)
    except Exception:
        return 0

    # Keywords that indicate the post is actionable (question, problem, comparison)
    actionable_patterns = [
        "?",  # questions
        "help", "issue", "problem", "error", "bug", "crash",
        "how to", "how do", "can i", "should i", "anyone",
        "alternative", "vs ", "compared to", "migrate", "switch",
        "not working", "doesn't work", "broken",
    ]

    for post in posts:
        score_val = post.get("score", 0)
        comments = post.get("num_comments", 0)
        title = post.get("title", "")
        body = post.get("selftext", "")
        text_lower = f"{title} {body}".lower()

        # Gate 1: minimum engagement
        if score_val < 3 and comments < 2:
            continue

        # Gate 2: must be actionable, not just a passing mention
        is_actionable = any(kw in text_lower for kw in actionable_patterns)
        if not is_actionable:
            continue

        engagement = (score_val + comments * 2)
        impact = min(1.0, engagement / 50)
        urgency = 0.5

        signal_type = post.get("signal_type", "pain_point")
        if signal_type == "product_mention":
            impact = min(1.0, impact * 1.2)

        result = ingest_signal(
            conn,
            source="reddit",
            signal_type=signal_type if signal_type in VALID_SIGNAL_TYPES else "pain_point",
            title=title or "Untitled",
            body=body[:500],
            url=post.get("url", ""),
            metadata={
                "subreddit": post.get("subreddit", ""),
                "score": score_val,
                "num_comments": comments,
            },
            impact=impact,
            urgency=urgency,
            confidence=0.6,
            ttl_hours=48,
        )
        if result:
            count += 1

    return count


def ingest_devto_signals(conn: DBConnection, config: Config) -> int:
    """Check Dev.to article stats for engagement spikes/drops."""
    if not config.has_devto:
        return 0

    from ..social.devto import DevToClient

    client = DevToClient(config)
    count = 0

    try:
        articles = client.get_all_stats()
    except Exception:
        return 0

    # Get stored stats from content_pieces
    stored = conn.execute(
        "SELECT slug, title, devto_article_id, devto_views, devto_reactions, devto_comments "
        "FROM content_pieces WHERE devto_article_id IS NOT NULL"
    ).fetchall()
    stored_map = {str(r["devto_article_id"]): dict(r) for r in stored}

    for article in articles:
        article_id = str(article.get("id", ""))
        if article_id not in stored_map:
            continue

        prev = stored_map[article_id]
        prev_views = prev.get("devto_views") or 0
        curr_views = article.get("page_views_count", 0) or article.get("views", 0)
        curr_reactions = article.get("public_reactions_count", 0) or article.get("reactions", 0)

        if prev_views > 0 and curr_views > prev_views * 1.5:
            # Engagement spike — topic is working
            result = ingest_signal(
                conn,
                source="devto_stats",
                signal_type="engagement_spike",
                title=f"Spike: {prev.get('title', article_id)} ({prev_views}→{curr_views} views)",
                body=f"Reactions: {curr_reactions}",
                url=f"https://dev.to/api/articles/{article_id}",
                metadata={
                    "article_id": article_id,
                    "slug": prev.get("slug", ""),
                    "prev_views": prev_views,
                    "curr_views": curr_views,
                    "curr_reactions": curr_reactions,
                },
                impact=0.8,
                urgency=0.6,
                confidence=0.9,
                ttl_hours=72,
            )
            if result:
                count += 1

        elif prev_views > 20 and curr_views <= prev_views * 1.05:
            # Engagement stalled — topic may not be worth repeating
            result = ingest_signal(
                conn,
                source="devto_stats",
                signal_type="engagement_drop",
                title=f"Stalled: {prev.get('title', article_id)} ({curr_views} views, flat)",
                body=f"Views flat at {curr_views}",
                url=f"https://dev.to/api/articles/{article_id}",
                metadata={
                    "article_id": article_id,
                    "slug": prev.get("slug", ""),
                    "curr_views": curr_views,
                },
                impact=0.3,
                urgency=0.2,
                confidence=0.7,
                ttl_hours=96,
            )
            if result:
                count += 1

    return count


def ingest_doc_change_signals(conn: DBConnection, config: Config) -> int:
    """Check for recently changed documentation pages."""
    count = 0
    since = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()

    try:
        changed = conn.execute(
            "SELECT url, path, doc_sha256, changed_from, fetched_at FROM doc_snapshots "
            "WHERE changed_from IS NOT NULL AND fetched_at >= ?",
            (since,),
        ).fetchall()
    except Exception:
        return 0

    for doc in changed:
        result = ingest_signal(
            conn,
            source="doc_change",
            signal_type="doc_gap",
            title=f"Doc changed: {doc['path']}",
            body=f"SHA256 changed from {(doc.get('changed_from') or '')[:12]} to {(doc.get('doc_sha256') or '')[:12]}",
            url=doc.get("url", ""),
            metadata={"path": doc["path"], "old_sha256": doc.get("changed_from"), "new_sha256": doc.get("doc_sha256")},
            impact=0.5,
            urgency=0.4,
            confidence=0.9,
            ttl_hours=96,
        )
        if result:
            count += 1

    return count


def ingest_scheduled_signals(conn: DBConnection) -> int:
    """Generate signals for periodic tasks that are due."""
    now = datetime.now(timezone.utc)
    count = 0

    # Content due: no content written in 5 days
    try:
        recent_content = conn.execute(
            "SELECT COUNT(*) as cnt FROM content_pieces WHERE created_at >= ?",
            ((now - timedelta(days=5)).isoformat(),),
        ).fetchone()
        if recent_content and recent_content["cnt"] == 0:
            result = ingest_signal(
                conn, source="schedule", signal_type="content_due",
                title="No content written in 5 days",
                impact=0.7, urgency=0.8, confidence=1.0, ttl_hours=24,
            )
            if result:
                count += 1
    except Exception:
        pass

    # Tweet due: no tweet in 2 days
    try:
        recent_tweets = conn.execute(
            "SELECT COUNT(*) as cnt FROM community_interactions WHERE channel = 'twitter' AND created_at >= ?",
            ((now - timedelta(days=2)).isoformat(),),
        ).fetchone()
        if recent_tweets and recent_tweets["cnt"] == 0:
            result = ingest_signal(
                conn, source="schedule", signal_type="tweet_due",
                title="No tweet posted in 2 days",
                impact=0.5, urgency=0.6, confidence=1.0, ttl_hours=12,
            )
            if result:
                count += 1
    except Exception:
        pass

    # Feedback due: no feedback in 7 days
    try:
        recent_feedback = conn.execute(
            "SELECT COUNT(*) as cnt FROM product_feedback WHERE created_at >= ?",
            ((now - timedelta(days=7)).isoformat(),),
        ).fetchone()
        if recent_feedback and recent_feedback["cnt"] == 0:
            result = ingest_signal(
                conn, source="schedule", signal_type="feedback_due",
                title="No feedback filed in 7 days",
                impact=0.5, urgency=0.5, confidence=1.0, ttl_hours=24,
            )
            if result:
                count += 1
    except Exception:
        pass

    return count


def run_all_producers(conn: DBConnection, config: Config) -> dict:
    """Run all signal producers and return ingestion counts.

    Note: agent-task issues are NOT part of the signal pipeline.
    They have their own workflow (agent-task.yml) that triggers on
    issue label, executes the task directly, and closes the issue.
    """
    ensure_signals_schema(conn)

    counts = {
        "github": ingest_github_signals(conn, config),
        "reddit": ingest_reddit_signals(conn, config),
        "devto": ingest_devto_signals(conn, config),
        "doc_changes": ingest_doc_change_signals(conn, config),
        "scheduled": ingest_scheduled_signals(conn),
    }
    counts["total"] = sum(counts.values())
    return counts
