"""Operational Reliability: idempotency, retries, circuit breakers, alerting.

Production systems don't just run once and hope. They:
- Retry transient failures with exponential backoff
- Track operation fingerprints for idempotency (don't run the same thing twice)
- Circuit-break when external services are down
- Alert operators when things go wrong
"""
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from functools import wraps

import requests

from ..config import Config
from ..db import now_iso


# ── Idempotency ────────────────────────────────────────────────────────

IDEMPOTENCY_SCHEMA = """
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    result_json TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS circuit_breakers (
    service TEXT PRIMARY KEY,
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_failure_at TEXT,
    state TEXT NOT NULL DEFAULT 'closed' CHECK(state IN ('closed', 'open', 'half_open')),
    opened_at TEXT
);

CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL CHECK(level IN ('info', 'warning', 'error', 'critical')),
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT,
    notified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alert_log_level ON alert_log(level);
"""


def init_reliability_db(db_conn):
    """Add reliability tables to the existing database."""
    db_conn.executescript(IDEMPOTENCY_SCHEMA)


def idempotency_key(operation: str, params: dict) -> str:
    """Generate a deterministic key for an operation + params."""
    content = json.dumps({"op": operation, "params": params}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def check_idempotency(db_conn, key: str) -> dict | None:
    """Check if an operation was already completed. Returns cached result or None."""
    init_reliability_db(db_conn)
    row = db_conn.execute(
        "SELECT result_json, expires_at FROM idempotency_keys WHERE key = ?", [key]
    ).fetchone()

    if not row:
        return None

    # Check expiry
    expires_at = row["expires_at"]
    if expires_at and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(timezone.utc):
        db_conn.execute("DELETE FROM idempotency_keys WHERE key = ?", [key])
        db_conn.commit()
        return None

    try:
        return json.loads(row["result_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def store_idempotency(db_conn, key: str, result: dict, ttl_hours: int = 24):
    """Store the result of an operation for idempotency."""
    init_reliability_db(db_conn)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
    db_conn.execute(
        "INSERT OR REPLACE INTO idempotency_keys (key, result_json, created_at, expires_at) VALUES (?, ?, ?, ?)",
        [key, json.dumps(result), now_iso(), expires_at],
    )
    db_conn.commit()


# ── Retry with Backoff ─────────────────────────────────────────────────

@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple = (requests.ConnectionError, requests.Timeout)
    retryable_status_codes: tuple = (429, 500, 502, 503, 504)


def retry_with_backoff(func=None, *, config: RetryConfig | None = None):
    """Decorator for retry with exponential backoff."""
    if config is None:
        config = RetryConfig()

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(config.max_retries + 1):
                try:
                    result = f(*args, **kwargs)
                    # Check for retryable HTTP status codes
                    if hasattr(result, 'status_code') and result.status_code in config.retryable_status_codes:
                        if attempt < config.max_retries:
                            delay = min(config.base_delay * (config.exponential_base ** attempt), config.max_delay)
                            # Respect Retry-After header
                            if hasattr(result, 'headers') and 'Retry-After' in result.headers:
                                try:
                                    delay = float(result.headers['Retry-After'])
                                except (ValueError, TypeError):
                                    pass
                            time.sleep(delay)
                            continue
                    return result
                except config.retryable_exceptions as e:
                    last_exception = e
                    if attempt < config.max_retries:
                        delay = min(config.base_delay * (config.exponential_base ** attempt), config.max_delay)
                        time.sleep(delay)
                    else:
                        raise
            if last_exception:
                raise last_exception
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


# ── Circuit Breaker ────────────────────────────────────────────────────

FAILURE_THRESHOLD = 5
RECOVERY_TIMEOUT_SECONDS = 300  # 5 minutes


def get_circuit_state(db_conn, service: str) -> str:
    """Get the circuit breaker state for a service."""
    init_reliability_db(db_conn)
    row = db_conn.execute(
        "SELECT state, failure_count, opened_at FROM circuit_breakers WHERE service = ?",
        [service],
    ).fetchone()

    if not row:
        return "closed"

    state = row["state"]

    # Check if open circuit should transition to half_open
    if state == "open" and row["opened_at"]:
        opened = datetime.fromisoformat(row["opened_at"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - opened).total_seconds() > RECOVERY_TIMEOUT_SECONDS:
            db_conn.execute(
                "UPDATE circuit_breakers SET state = 'half_open' WHERE service = ?",
                [service],
            )
            db_conn.commit()
            return "half_open"

    return state


def record_success(db_conn, service: str):
    """Record a successful call; reset failure count."""
    init_reliability_db(db_conn)
    db_conn.execute(
        "INSERT OR REPLACE INTO circuit_breakers (service, failure_count, state, last_failure_at, opened_at) "
        "VALUES (?, 0, 'closed', NULL, NULL)",
        [service],
    )
    db_conn.commit()


def record_failure(db_conn, service: str):
    """Record a failed call; potentially open the circuit."""
    init_reliability_db(db_conn)
    row = db_conn.execute(
        "SELECT failure_count FROM circuit_breakers WHERE service = ?", [service]
    ).fetchone()

    count = (row["failure_count"] + 1) if row else 1
    now = now_iso()

    if count >= FAILURE_THRESHOLD:
        db_conn.execute(
            "INSERT OR REPLACE INTO circuit_breakers (service, failure_count, state, last_failure_at, opened_at) "
            "VALUES (?, ?, 'open', ?, ?)",
            [service, count, now, now],
        )
    else:
        db_conn.execute(
            "INSERT OR REPLACE INTO circuit_breakers (service, failure_count, state, last_failure_at, opened_at) "
            "VALUES (?, ?, 'closed', ?, NULL)",
            [service, count, now],
        )
    db_conn.commit()


def is_service_available(db_conn, service: str) -> bool:
    """Check if a service is available (circuit not open)."""
    state = get_circuit_state(db_conn, service)
    return state != "open"


# ── Alerting ───────────────────────────────────────────────────────────

def log_alert(db_conn, level: str, source: str, message: str, details: dict | None = None):
    """Log an alert to the database."""
    init_reliability_db(db_conn)
    db_conn.execute(
        "INSERT INTO alert_log (level, source, message, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
        [level, source, message, json.dumps(details or {}), now_iso()],
    )
    db_conn.commit()


def send_webhook_alert(webhook_url: str, level: str, source: str, message: str):
    """Send an alert via webhook (Slack, Discord, etc.)."""
    if not webhook_url:
        return

    payload = {
        "text": f"[{level.upper()}] {source}: {message}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*[{level.upper()}]* `{source}`\n{message}",
                },
            }
        ],
    }

    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except requests.RequestException:
        pass  # Alert delivery is best-effort


def get_recent_alerts(db_conn, level: str | None = None, limit: int = 50) -> list[dict]:
    """Get recent alerts from the log."""
    init_reliability_db(db_conn)
    if level:
        rows = db_conn.execute(
            "SELECT * FROM alert_log WHERE level = ? ORDER BY created_at DESC LIMIT ?",
            [level, limit],
        ).fetchall()
    else:
        rows = db_conn.execute(
            "SELECT * FROM alert_log ORDER BY created_at DESC LIMIT ?", [limit]
        ).fetchall()
    return [dict(r) for r in rows]


def format_alert_dashboard(db_conn) -> str:
    """Generate a markdown alert dashboard."""
    init_reliability_db(db_conn)

    # Count by level
    counts = {}
    for level in ("critical", "error", "warning", "info"):
        row = db_conn.execute(
            "SELECT COUNT(*) FROM alert_log WHERE level = ?", [level]
        ).fetchone()
        counts[level] = row[0]

    # Circuit breaker states
    breakers = db_conn.execute("SELECT * FROM circuit_breakers").fetchall()

    lines = [
        "# Operational Dashboard",
        "",
        "## Alert Summary",
        "| Level | Count |",
        "|-------|-------|",
    ]
    for level, count in counts.items():
        lines.append(f"| {level.title()} | {count} |")

    lines.extend(["", "## Circuit Breakers", "| Service | State | Failures |", "|---------|-------|----------|"])
    if breakers:
        for b in breakers:
            b = dict(b)
            lines.append(f"| {b['service']} | {b['state']} | {b['failure_count']} |")
    else:
        lines.append("| (none) | -- | -- |")

    # Recent alerts
    recent = get_recent_alerts(db_conn, limit=10)
    if recent:
        lines.extend(["", "## Recent Alerts"])
        for alert in recent:
            lines.append(f"- **[{alert['level'].upper()}]** {alert['source']}: {alert['message']} ({alert['created_at'][:19]})")

    return "\n".join(lines)
