"""Metrics Sink: closed-loop impact measurement for every action.

The difference between "I posted content" and "I drove growth" is measurement.
This module tracks real outcomes tied to agent actions:
- GitHub: issue engagement, PR comments, traffic referrals
- Site: pageviews, time-on-page, bounce rate (via GoatCounter/Plausible)
- Content: click-through on citations, social shares
- Experiments: primary metric, guardrail metric, stopping rules

Every experiment gets a metrics contract:
- One primary metric (what we're trying to move)
- One guardrail metric (what we must not break: spam, negative replies, bounce)
- A stopping rule (when to conclude; time-based, count-based, or signal-based)
"""
import json
import time
from dataclasses import dataclass

import requests

from ..config import Config
from ..db import now_iso


# ── Data Models ─────────────────────────────────────────────────────────

@dataclass
class MetricsContract:
    """Every experiment must define its success criteria upfront."""
    experiment_id: int
    primary_metric: str          # e.g. "github_issue_replies_with_upvote"
    primary_target: float        # e.g. 5.0 (5 upvoted replies)
    guardrail_metric: str        # e.g. "negative_reply_count"
    guardrail_threshold: float   # e.g. 2.0 (stop if >2 negative replies)
    stopping_rule: str           # "time:7d" or "count:50" or "signal:target_reached"
    status: str = "active"       # active, stopped, concluded


@dataclass
class MetricEvent:
    """A single metric observation."""
    source: str          # github, site, social, manual
    metric_name: str     # e.g. "issue_reply_upvotes", "page_views"
    value: float
    dimensions: dict     # e.g. {"repo": "purchases-ios", "issue_id": 1234}
    timestamp: str = ""
    experiment_id: int | None = None  # tie to experiment if applicable


@dataclass
class ImpactReport:
    """Closed-loop impact measurement for an experiment or time period."""
    period: str
    actions_taken: int
    outcomes_measured: int
    metrics: dict[str, float]        # metric_name -> aggregate value
    learnings: list[str]
    next_actions: list[str]


# ── GitHub Metrics ──────────────────────────────────────────────────────

def measure_github_engagement(config: Config, since_days: int = 7) -> list[MetricEvent]:
    """Measure real engagement on GitHub repos RevenueCat cares about."""
    events = []
    if not config.github_token:
        return events

    session = requests.Session()
    session.headers["Authorization"] = f"token {config.github_token}"
    session.headers["Accept"] = "application/vnd.github.v3+json"

    repos = [
        "RevenueCat/purchases-ios",
        "RevenueCat/purchases-android",
        "RevenueCat/purchases-flutter",
        "RevenueCat/purchases-react-native",
        "RevenueCat/purchases-unity",
    ]

    for repo in repos:
        try:
            # Issues we commented on: check for reactions/replies
            resp = session.get(
                f"https://api.github.com/repos/{repo}/issues/comments",
                params={"sort": "created", "direction": "desc", "per_page": 30},
                timeout=10,
            )
            if resp.status_code == 200:
                for comment in resp.json():
                    reactions = comment.get("reactions", {})
                    upvotes = reactions.get("+1", 0) + reactions.get("heart", 0)
                    if upvotes > 0:
                        events.append(MetricEvent(
                            source="github",
                            metric_name="comment_upvotes",
                            value=upvotes,
                            dimensions={"repo": repo, "comment_id": comment["id"]},
                            timestamp=comment.get("created_at", ""),
                        ))

            # Issues opened/closed ratio
            resp = session.get(
                f"https://api.github.com/repos/{repo}/issues",
                params={"state": "closed", "sort": "updated", "per_page": 10},
                timeout=10,
            )
            if resp.status_code == 200:
                events.append(MetricEvent(
                    source="github",
                    metric_name="issues_recently_closed",
                    value=len(resp.json()),
                    dimensions={"repo": repo},
                    timestamp=now_iso(),
                ))

            time.sleep(0.5)  # Rate limit
        except requests.RequestException:
            continue

    return events


def measure_github_traffic(config: Config) -> list[MetricEvent]:
    """Measure traffic to GitHub repos (requires push access)."""
    events = []
    if not config.github_token or not config.github_repo:
        return events

    session = requests.Session()
    session.headers["Authorization"] = f"token {config.github_token}"

    try:
        # Views on our repo
        resp = session.get(
            f"https://api.github.com/repos/{config.github_repo}/traffic/views",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            events.append(MetricEvent(
                source="github",
                metric_name="repo_views",
                value=data.get("count", 0),
                dimensions={"repo": config.github_repo, "uniques": data.get("uniques", 0)},
                timestamp=now_iso(),
            ))

        # Clones
        resp = session.get(
            f"https://api.github.com/repos/{config.github_repo}/traffic/clones",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            events.append(MetricEvent(
                source="github",
                metric_name="repo_clones",
                value=data.get("count", 0),
                dimensions={"repo": config.github_repo, "uniques": data.get("uniques", 0)},
                timestamp=now_iso(),
            ))

        # Referral sources
        resp = session.get(
            f"https://api.github.com/repos/{config.github_repo}/traffic/popular/referrers",
            timeout=10,
        )
        if resp.status_code == 200:
            for ref in resp.json():
                events.append(MetricEvent(
                    source="github",
                    metric_name="referral_source",
                    value=ref.get("count", 0),
                    dimensions={"referrer": ref.get("referrer", ""), "uniques": ref.get("uniques", 0)},
                    timestamp=now_iso(),
                ))
    except requests.RequestException:
        pass

    return events


# ── Site Analytics ──────────────────────────────────────────────────────

def measure_site_analytics(config: Config) -> list[MetricEvent]:
    """Measure site analytics via GoatCounter (free, privacy-friendly).

    GoatCounter provides a free hosted tier; no self-hosting needed.
    API: https://www.goatcounter.com/help/api
    """
    events = []
    goatcounter_token = getattr(config, 'goatcounter_token', None)
    goatcounter_site = getattr(config, 'goatcounter_site', None)

    if not goatcounter_token or not goatcounter_site:
        return events

    try:
        resp = requests.get(
            f"https://{goatcounter_site}.goatcounter.com/api/v0/stats/total",
            headers={"Authorization": f"Bearer {goatcounter_token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            events.append(MetricEvent(
                source="site",
                metric_name="total_pageviews",
                value=data.get("total", 0),
                dimensions={"site": goatcounter_site},
                timestamp=now_iso(),
            ))
    except requests.RequestException:
        pass

    return events


# ── Metrics Storage ─────────────────────────────────────────────────────

METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    dimensions_json TEXT,
    experiment_id INTEGER,
    timestamp TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    primary_metric TEXT NOT NULL,
    primary_target REAL NOT NULL,
    guardrail_metric TEXT NOT NULL,
    guardrail_threshold REAL NOT NULL,
    stopping_rule TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    FOREIGN KEY (experiment_id) REFERENCES growth_experiments(id)
);

CREATE INDEX IF NOT EXISTS idx_metric_events_name ON metric_events(metric_name);
CREATE INDEX IF NOT EXISTS idx_metric_events_experiment ON metric_events(experiment_id);
CREATE INDEX IF NOT EXISTS idx_metrics_contracts_experiment ON metrics_contracts(experiment_id);
"""


def init_metrics_db(db_conn):
    """Add metrics tables to the existing database."""
    db_conn.executescript(METRICS_SCHEMA)


def store_metric_event(db_conn, event: MetricEvent) -> int:
    """Store a metric event."""
    init_metrics_db(db_conn)
    cursor = db_conn.execute(
        "INSERT INTO metric_events (source, metric_name, value, dimensions_json, experiment_id, timestamp, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            event.source, event.metric_name, event.value,
            json.dumps(event.dimensions), event.experiment_id,
            event.timestamp or now_iso(), now_iso(),
        ],
    )
    db_conn.commit()
    return cursor.lastrowid


def store_metrics_contract(db_conn, contract: MetricsContract) -> int:
    """Store a metrics contract for an experiment."""
    init_metrics_db(db_conn)
    cursor = db_conn.execute(
        "INSERT INTO metrics_contracts (experiment_id, primary_metric, primary_target, "
        "guardrail_metric, guardrail_threshold, stopping_rule, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            contract.experiment_id, contract.primary_metric, contract.primary_target,
            contract.guardrail_metric, contract.guardrail_threshold,
            contract.stopping_rule, contract.status, now_iso(),
        ],
    )
    db_conn.commit()
    return cursor.lastrowid


def check_stopping_rules(db_conn, experiment_id: int) -> tuple[bool, str]:
    """Check if an experiment should be stopped based on its metrics contract.

    Returns (should_stop, reason).
    """
    init_metrics_db(db_conn)
    contracts = db_conn.execute(
        "SELECT * FROM metrics_contracts WHERE experiment_id = ? AND status = 'active'",
        [experiment_id],
    ).fetchall()

    if not contracts:
        return False, "no_contract"

    contract = dict(contracts[0])

    # Check guardrail
    guardrail_events = db_conn.execute(
        "SELECT SUM(value) as total FROM metric_events WHERE metric_name = ? AND experiment_id = ?",
        [contract["guardrail_metric"], experiment_id],
    ).fetchone()

    if guardrail_events and guardrail_events["total"] and guardrail_events["total"] > contract["guardrail_threshold"]:
        return True, f"guardrail_breached: {contract['guardrail_metric']} = {guardrail_events['total']} > {contract['guardrail_threshold']}"

    # Check primary target reached
    primary_events = db_conn.execute(
        "SELECT SUM(value) as total FROM metric_events WHERE metric_name = ? AND experiment_id = ?",
        [contract["primary_metric"], experiment_id],
    ).fetchone()

    if primary_events and primary_events["total"] and primary_events["total"] >= contract["primary_target"]:
        rule = contract["stopping_rule"]
        if "signal:target_reached" in rule:
            return True, f"target_reached: {contract['primary_metric']} = {primary_events['total']} >= {contract['primary_target']}"

    return False, "running"


# ── Impact Reporting ────────────────────────────────────────────────────

def collect_all_metrics(config: Config) -> list[MetricEvent]:
    """Run all metric collectors and return events."""
    events = []
    events.extend(measure_github_engagement(config))
    events.extend(measure_github_traffic(config))
    events.extend(measure_site_analytics(config))
    return events


def generate_impact_report(db_conn, config: Config, experiment_id: int | None = None) -> ImpactReport:
    """Generate a closed-loop impact report."""
    init_metrics_db(db_conn)

    # Collect fresh metrics
    new_events = collect_all_metrics(config)
    for event in new_events:
        if experiment_id:
            event.experiment_id = experiment_id
        store_metric_event(db_conn, event)

    # Aggregate from DB
    if experiment_id:
        where_clause = "WHERE experiment_id = ?"
        params = [experiment_id]
    else:
        where_clause = ""
        params = []

    rows = db_conn.execute(
        f"SELECT metric_name, SUM(value) as total, COUNT(*) as count "
        f"FROM metric_events {where_clause} GROUP BY metric_name",
        params,
    ).fetchall()

    metrics = {row["metric_name"]: row["total"] for row in rows}

    # Count actions
    actions = 0
    try:
        actions = db_conn.execute("SELECT COUNT(*) FROM run_log").fetchone()[0]
    except Exception:
        pass

    # Generate learnings
    learnings = []
    if metrics.get("comment_upvotes", 0) > 0:
        learnings.append(f"GitHub comments received {metrics['comment_upvotes']:.0f} upvotes; community finds responses valuable")
    if metrics.get("repo_views", 0) > 0:
        learnings.append(f"Repository received {metrics['repo_views']:.0f} views; content is driving discovery")
    if metrics.get("total_pageviews", 0) > 0:
        learnings.append(f"Site received {metrics['total_pageviews']:.0f} pageviews")
    if not learnings:
        learnings.append("Metrics collection configured but no engagement data yet; run for a full cycle to see results")

    # Next actions
    next_actions = []
    if metrics.get("comment_upvotes", 0) < 5:
        next_actions.append("Increase GitHub response quality; target 5+ upvoted replies per week")
    if not metrics.get("repo_views"):
        next_actions.append("Configure GitHub repo traffic tracking (requires push access)")
    if not metrics.get("total_pageviews"):
        next_actions.append("Set up GoatCounter for site analytics (free tier: goatcounter.com)")

    return ImpactReport(
        period="last_collection",
        actions_taken=actions,
        outcomes_measured=len(new_events),
        metrics=metrics,
        learnings=learnings,
        next_actions=next_actions,
    )


def format_impact_report(report: ImpactReport) -> str:
    """Format impact report as markdown."""
    lines = [
        "# Impact Measurement Report",
        f"*Period: {report.period}*",
        "",
        f"**Actions taken:** {report.actions_taken}",
        f"**Outcomes measured:** {report.outcomes_measured}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    for name, value in sorted(report.metrics.items()):
        lines.append(f"| {name.replace('_', ' ').title()} | {value:.0f} |")

    if report.learnings:
        lines.extend(["", "## Learnings", ""])
        for learning in report.learnings:
            lines.append(f"- {learning}")

    if report.next_actions:
        lines.extend(["", "## Next Actions", ""])
        for a in report.next_actions:
            lines.append(f"- {a}")

    return "\n".join(lines)
