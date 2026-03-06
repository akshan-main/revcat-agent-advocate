"""Competitive Intelligence: weekly digest format with clear boundaries.

This is NOT surveillance. This is public-data competitive awareness:
- Monitor public pricing pages, changelogs, and blog posts
- Weekly digest format (not real-time stalking)
- "So what" section: what does this mean for RevenueCat's positioning?
- Clear sourcing: every claim links to a public URL
- Boundaries: no scraping private data, no reverse engineering, no dark patterns
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

from ..config import Config
from ..db import now_iso


# ── Public Data Sources Only ───────────────────────────────────────────

COMPETITORS = {
    "adapty": {
        "name": "Adapty",
        "pricing_url": "https://adapty.io/pricing/",
        "changelog_url": "https://adapty.io/blog/",
        "docs_url": "https://docs.adapty.io/",
    },
    "qonversion": {
        "name": "Qonversion",
        "pricing_url": "https://qonversion.io/pricing/",
        "changelog_url": "https://qonversion.io/blog/",
        "docs_url": "https://documentation.qonversion.io/",
    },
    "glassfy": {
        "name": "Glassfy",
        "pricing_url": "https://glassfy.io/pricing/",
        "changelog_url": "https://glassfy.io/blog/",
        "docs_url": "https://docs.glassfy.io/",
    },
    "superwall": {
        "name": "Superwall",
        "pricing_url": "https://superwall.com/pricing",
        "changelog_url": "https://superwall.com/blog",
        "docs_url": "https://docs.superwall.com/",
    },
}

# Boundaries: what we will NOT do
BOUNDARIES = """
Competitive Intelligence Boundaries:
1. Public data only: pricing pages, blogs, changelogs, docs
2. No scraping behind authentication
3. No reverse engineering SDKs or APIs
4. No impersonation or fake accounts
5. No real-time monitoring or alerting on competitors
6. Weekly digest cadence only, not reactive
7. Focus on "so what for RevenueCat," not competitor bashing
"""


@dataclass
class CompetitorSignal:
    """A single competitive signal from a public source."""
    competitor: str
    signal_type: str       # pricing_change, feature_launch, blog_post, sdk_update
    title: str
    summary: str
    source_url: str
    relevance: str         # how this relates to RevenueCat
    so_what: str           # actionable takeaway
    detected_at: str = ""


@dataclass
class CompetitiveDigest:
    """Weekly competitive intelligence digest."""
    week_of: str
    signals: list[CompetitorSignal] = field(default_factory=list)
    market_summary: str = ""
    rc_positioning: str = ""
    action_items: list[str] = field(default_factory=list)


# ── Public Page Checks ─────────────────────────────────────────────────

def _fetch_public_page(url: str, timeout: int = 10) -> str | None:
    """Fetch a public URL. Returns page text or None."""
    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "revcat-agent-advocate/1.0 (competitive-digest; public-data-only)"
        })
        if resp.status_code == 200:
            return resp.text
    except requests.RequestException:
        pass
    return None


def _extract_page_title(html: str) -> str:
    """Extract title from HTML."""
    match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def check_pricing_page(competitor_key: str) -> CompetitorSignal | None:
    """Check a competitor's public pricing page for notable info."""
    comp = COMPETITORS.get(competitor_key)
    if not comp:
        return None

    html = _fetch_public_page(comp["pricing_url"])
    if not html:
        return None

    _extract_page_title(html)

    # Look for pricing signals in the text
    text = re.sub(r'<[^>]+>', ' ', html).lower()

    pricing_keywords = ["free", "starter", "pro", "enterprise", "per month", "per year",
                        "mtr", "monthly tracked revenue", "mau", "/mo", "/yr"]
    found = [kw for kw in pricing_keywords if kw in text]

    if found:
        return CompetitorSignal(
            competitor=comp["name"],
            signal_type="pricing_snapshot",
            title=f"{comp['name']} pricing page snapshot",
            summary=f"Pricing page mentions: {', '.join(found[:5])}",
            source_url=comp["pricing_url"],
            relevance="Pricing model comparison",
            so_what=f"Compare {comp['name']}'s pricing tiers with RevenueCat's current offering",
            detected_at=now_iso(),
        )

    return None


def check_changelog(competitor_key: str) -> CompetitorSignal | None:
    """Check a competitor's public blog/changelog for recent posts."""
    comp = COMPETITORS.get(competitor_key)
    if not comp:
        return None

    html = _fetch_public_page(comp["changelog_url"])
    if not html:
        return None

    _extract_page_title(html)

    # Extract recent post titles (basic heuristic)
    h2_matches = re.findall(r'<h[23][^>]*>([^<]+)</h[23]>', html, re.IGNORECASE)
    recent_titles = [t.strip() for t in h2_matches[:5] if len(t.strip()) > 10]

    if recent_titles:
        return CompetitorSignal(
            competitor=comp["name"],
            signal_type="blog_snapshot",
            title=f"{comp['name']} recent content",
            summary=f"Recent posts: {'; '.join(recent_titles[:3])}",
            source_url=comp["changelog_url"],
            relevance="Content strategy and feature announcements",
            so_what=f"Review {comp['name']}'s messaging: identify gaps or differentiators for RC content",
            detected_at=now_iso(),
        )

    return None


# ── Digest Generation ──────────────────────────────────────────────────

def generate_competitive_digest(config: Config) -> CompetitiveDigest:
    """Generate a weekly competitive digest from public sources only.

    This intentionally operates at weekly cadence and only uses
    publicly available data. See BOUNDARIES constant for guardrails.

    In demo mode, returns a digest with sample data instead of making
    live HTTP requests to competitor websites.
    """
    digest = CompetitiveDigest(
        week_of=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )

    if getattr(config, "demo_mode", False):
        # Return sample digest without live network requests
        digest.market_summary = "Demo mode: no live competitor data fetched."
        digest.rc_positioning = "Maintain current positioning emphasis."
        return digest

    for key in COMPETITORS:
        # Check pricing pages
        signal = check_pricing_page(key)
        if signal:
            digest.signals.append(signal)

        # Check blogs/changelogs
        signal = check_changelog(key)
        if signal:
            digest.signals.append(signal)

    # Generate summary
    if digest.signals:
        digest.market_summary = (
            f"Collected {len(digest.signals)} public signals from "
            f"{len(set(s.competitor for s in digest.signals))} competitors this week."
        )
        digest.rc_positioning = (
            "RevenueCat differentiators to emphasize: MCP server for AI agents, "
            "Charts API with programmatic access, comprehensive multi-platform SDK support, "
            "and the LLM-optimized documentation index."
        )
        digest.action_items = [
            s.so_what for s in digest.signals if s.so_what
        ]
    else:
        digest.market_summary = "No new public signals detected this week."
        digest.rc_positioning = "Maintain current positioning emphasis."

    return digest


# ── Formatting ─────────────────────────────────────────────────────────

def format_competitive_digest(digest: CompetitiveDigest) -> str:
    """Format digest as markdown report."""
    lines = [
        f"# Competitive Intelligence Digest: Week of {digest.week_of}",
        "",
        "---",
        "*Public data only. See boundaries below.*",
        "",
        "## Market Summary",
        digest.market_summary,
        "",
        "## Signals",
        "",
    ]

    if digest.signals:
        for signal in digest.signals:
            lines.extend([
                f"### {signal.competitor}: {signal.title}",
                f"*Type: {signal.signal_type} | Source: [{signal.source_url}]({signal.source_url})*",
                "",
                signal.summary,
                "",
                f"**So what:** {signal.so_what}",
                "",
            ])
    else:
        lines.append("No new signals this week.")
        lines.append("")

    lines.extend([
        "## RevenueCat Positioning",
        digest.rc_positioning,
        "",
    ])

    if digest.action_items:
        lines.append("## Action Items")
        for item in digest.action_items:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend([
        "---",
        "## Boundaries",
        BOUNDARIES,
    ])

    return "\n".join(lines)
