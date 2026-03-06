"""Distribution Pipeline: get content in front of the right people.

DevRel is not "write posts." DevRel is "get the right post in front of the
right people and learn what happened."

Pipeline: draft → queued → approved → posted → measured

Features:
- Channel-aware formatting (GitHub issue vs tweet vs Reddit comment)
- Rate limits per channel (no spam)
- Deduplication (never post the same thing twice)
- Preview before posting (human-in-the-loop by default)
- Scheduling (spread posts over time, not all at once)
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from ..config import Config
from ..db import init_db, now_iso


# ── Distribution Schema ─────────────────────────────────────────────────

DISTRIBUTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS distribution_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL CHECK(channel IN ('github_issue', 'github_comment', 'github_discussion', 'twitter', 'reddit', 'dev_to', 'hashnode')),
    content_hash TEXT NOT NULL,
    title TEXT,
    body TEXT NOT NULL,
    target_url TEXT,
    metadata_json TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'queued', 'approved', 'posted', 'skipped', 'failed')),
    scheduled_at TEXT,
    posted_at TEXT,
    post_url TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(channel, content_hash)
);

CREATE TABLE IF NOT EXISTS distribution_rate_limits (
    channel TEXT PRIMARY KEY,
    max_per_hour INTEGER NOT NULL DEFAULT 2,
    max_per_day INTEGER NOT NULL DEFAULT 10,
    cooldown_minutes INTEGER NOT NULL DEFAULT 30,
    last_posted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_dist_queue_status ON distribution_queue(status);
CREATE INDEX IF NOT EXISTS idx_dist_queue_channel ON distribution_queue(channel);
"""

# Default rate limits per channel
DEFAULT_RATE_LIMITS = {
    "github_issue": {"max_per_hour": 2, "max_per_day": 5, "cooldown_minutes": 30},
    "github_comment": {"max_per_hour": 5, "max_per_day": 20, "cooldown_minutes": 10},
    "github_discussion": {"max_per_hour": 2, "max_per_day": 5, "cooldown_minutes": 30},
    "twitter": {"max_per_hour": 3, "max_per_day": 10, "cooldown_minutes": 20},
    "reddit": {"max_per_hour": 2, "max_per_day": 8, "cooldown_minutes": 30},
    "dev_to": {"max_per_hour": 1, "max_per_day": 2, "cooldown_minutes": 60},
    "hashnode": {"max_per_hour": 1, "max_per_day": 2, "cooldown_minutes": 60},
}


@dataclass
class DistributionItem:
    """A piece of content queued for distribution."""
    channel: str
    title: str
    body: str
    target_url: str = ""
    metadata: dict = field(default_factory=dict)
    scheduled_at: str | None = None


def init_distribution_db(db_conn):
    """Add distribution tables to the existing database."""
    db_conn.executescript(DISTRIBUTION_SCHEMA)
    # Seed rate limits
    for channel, limits in DEFAULT_RATE_LIMITS.items():
        db_conn.execute(
            "INSERT OR IGNORE INTO distribution_rate_limits (channel, max_per_hour, max_per_day, cooldown_minutes) "
            "VALUES (?, ?, ?, ?)",
            [channel, limits["max_per_hour"], limits["max_per_day"], limits["cooldown_minutes"]],
        )
    db_conn.commit()


def _content_hash(channel: str, body: str) -> str:
    """Hash content to detect duplicates."""
    return hashlib.sha256(f"{channel}:{body.strip()[:500]}".encode()).hexdigest()[:16]


# ── Queue Management ────────────────────────────────────────────────────

def enqueue(db_conn, item: DistributionItem) -> int | None:
    """Add content to the distribution queue. Returns ID or None if duplicate."""
    init_distribution_db(db_conn)
    content_hash = _content_hash(item.channel, item.body)

    # Dedup check
    existing = db_conn.execute(
        "SELECT id FROM distribution_queue WHERE channel = ? AND content_hash = ?",
        [item.channel, content_hash],
    ).fetchone()

    if existing:
        return None  # Duplicate

    cursor = db_conn.execute(
        "INSERT INTO distribution_queue (channel, content_hash, title, body, target_url, "
        "metadata_json, status, scheduled_at, created_at) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
        [
            item.channel, content_hash, item.title, item.body,
            item.target_url, json.dumps(item.metadata),
            item.scheduled_at, now_iso(),
        ],
    )
    db_conn.commit()
    return cursor.lastrowid


def approve(db_conn, item_id: int):
    """Mark a queued item as approved for posting."""
    db_conn.execute(
        "UPDATE distribution_queue SET status = 'approved' WHERE id = ? AND status IN ('draft', 'queued')",
        [item_id],
    )
    db_conn.commit()


def approve_all_drafts(db_conn, channel: str | None = None):
    """Approve all draft items, optionally filtered by channel."""
    if channel:
        db_conn.execute(
            "UPDATE distribution_queue SET status = 'approved' WHERE status = 'draft' AND channel = ?",
            [channel],
        )
    else:
        db_conn.execute(
            "UPDATE distribution_queue SET status = 'approved' WHERE status = 'draft'",
        )
    db_conn.commit()


def skip(db_conn, item_id: int, reason: str = ""):
    """Skip a queued item."""
    db_conn.execute(
        "UPDATE distribution_queue SET status = 'skipped', error = ? WHERE id = ?",
        [reason, item_id],
    )
    db_conn.commit()


def get_queue(db_conn, status: str | None = None, channel: str | None = None) -> list[dict]:
    """Get items from the distribution queue."""
    init_distribution_db(db_conn)
    query = "SELECT * FROM distribution_queue"
    conditions = []
    params = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if channel:
        conditions.append("channel = ?")
        params.append(channel)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC"

    return [dict(row) for row in db_conn.execute(query, params).fetchall()]


# ── Rate Limiting ───────────────────────────────────────────────────────

def check_rate_limit(db_conn, channel: str) -> tuple[bool, str]:
    """Check if posting to this channel is rate-limited. Returns (allowed, reason)."""
    init_distribution_db(db_conn)

    limits = db_conn.execute(
        "SELECT * FROM distribution_rate_limits WHERE channel = ?", [channel]
    ).fetchone()

    if not limits:
        return True, "no_limits_configured"

    now = datetime.now(timezone.utc)

    # Check cooldown
    last_posted = limits["last_posted_at"]
    if last_posted:
        last_dt = datetime.fromisoformat(last_posted.replace("Z", "+00:00"))
        cooldown = timedelta(minutes=limits["cooldown_minutes"])
        if now - last_dt < cooldown:
            remaining = cooldown - (now - last_dt)
            return False, f"cooldown: {remaining.seconds // 60}m remaining"

    # Check hourly limit
    hour_ago = (now - timedelta(hours=1)).isoformat()
    hourly = db_conn.execute(
        "SELECT COUNT(*) FROM distribution_queue WHERE channel = ? AND status = 'posted' AND posted_at > ?",
        [channel, hour_ago],
    ).fetchone()[0]

    if hourly >= limits["max_per_hour"]:
        return False, f"hourly_limit: {hourly}/{limits['max_per_hour']}"

    # Check daily limit
    day_ago = (now - timedelta(days=1)).isoformat()
    daily = db_conn.execute(
        "SELECT COUNT(*) FROM distribution_queue WHERE channel = ? AND status = 'posted' AND posted_at > ?",
        [channel, day_ago],
    ).fetchone()[0]

    if daily >= limits["max_per_day"]:
        return False, f"daily_limit: {daily}/{limits['max_per_day']}"

    return True, "ok"


def record_post(db_conn, item_id: int, post_url: str = ""):
    """Record that an item was posted."""
    now = now_iso()
    db_conn.execute(
        "UPDATE distribution_queue SET status = 'posted', posted_at = ?, post_url = ? WHERE id = ?",
        [now, post_url, item_id],
    )
    # Update rate limit tracker
    item = db_conn.execute("SELECT channel FROM distribution_queue WHERE id = ?", [item_id]).fetchone()
    if item:
        db_conn.execute(
            "UPDATE distribution_rate_limits SET last_posted_at = ? WHERE channel = ?",
            [now, item["channel"]],
        )
    db_conn.commit()


def record_failure(db_conn, item_id: int, error: str):
    """Record that posting failed."""
    db_conn.execute(
        "UPDATE distribution_queue SET status = 'failed', error = ? WHERE id = ?",
        [error, item_id],
    )
    db_conn.commit()


# ── Channel Formatters ──────────────────────────────────────────────────

def format_for_channel(content: str, channel: str, title: str = "") -> str:
    """Format content for a specific channel's conventions."""
    if channel == "twitter":
        # Twitter: 280 chars, no markdown, link at end
        plain = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)  # Strip markdown links
        plain = re.sub(r'[#*_`]', '', plain)  # Strip markdown formatting
        if len(plain) > 260:
            plain = plain[:257] + "..."
        return plain

    elif channel in ("github_issue", "github_comment", "github_discussion"):
        # GitHub: full markdown, add attribution footer
        footer = "\n\n---\n*Drafted by [Advocate OS](https://github.com/), verified against official RevenueCat docs*"
        return content + footer

    elif channel == "reddit":
        # Reddit: markdown, but no H1 (looks weird in comments)
        formatted = re.sub(r'^# ', '## ', content, flags=re.MULTILINE)
        return formatted

    elif channel in ("dev_to", "hashnode"):
        # Blog platforms: full markdown with front matter
        return content

    return content


# ── Preview ─────────────────────────────────────────────────────────────

def preview_queue(db_conn, limit: int = 20) -> str:
    """Generate a human-readable preview of the distribution queue."""
    items = get_queue(db_conn)[:limit]
    if not items:
        return "Distribution queue is empty."

    lines = ["# Distribution Queue Preview", ""]
    status_counts = {}
    for item in items:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1

    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    for status, count in sorted(status_counts.items()):
        lines.append(f"| {status} | {count} |")
    lines.append("")

    for item in items:
        emoji = {"draft": "📝", "queued": "⏳", "approved": "✅", "posted": "🚀", "skipped": "⏭️", "failed": "❌"}.get(item["status"], "❓")
        lines.append(f"### {emoji} [{item['channel']}] {item.get('title', 'Untitled')}")
        lines.append(f"Status: {item['status']} | Created: {item['created_at'][:10]}")
        body_preview = (item.get("body", ""))[:200]
        lines.append(f"> {body_preview}...")
        if item.get("post_url"):
            lines.append(f"Posted: {item['post_url']}")
        lines.append("")

    return "\n".join(lines)
