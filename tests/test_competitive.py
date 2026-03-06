"""Tests for competitive intelligence: digest format with boundaries."""
from advocate.intelligence.competitive import (
    generate_competitive_digest,
    format_competitive_digest,
    _extract_page_title,
    CompetitorSignal,
    CompetitiveDigest,
    COMPETITORS,
    BOUNDARIES,
)


def test_extract_page_title():
    assert _extract_page_title("<title>Pricing - Adapty</title>") == "Pricing - Adapty"
    assert _extract_page_title("<html><body>no title</body></html>") == ""


def test_generate_digest_returns_digest(mock_config):
    """Digest generation works regardless of HTTP availability."""
    digest = generate_competitive_digest(mock_config)
    assert isinstance(digest, CompetitiveDigest)
    assert digest.week_of  # Date is always set
    # Signals may be 0 if public pages are unreachable (CI, offline)
    assert isinstance(digest.signals, list)
    assert isinstance(digest.action_items, list)


def test_format_digest():
    digest = CompetitiveDigest(
        week_of="2026-03-05",
        signals=[
            CompetitorSignal(
                competitor="Adapty",
                signal_type="pricing_snapshot",
                title="Adapty pricing update",
                summary="New tier added",
                source_url="https://adapty.io/pricing/",
                relevance="Pricing comparison",
                so_what="Compare with RC pricing",
                detected_at="2026-03-05T00:00:00Z",
            ),
        ],
        market_summary="1 signal detected.",
        rc_positioning="MCP server is unique.",
        action_items=["Compare pricing"],
    )
    md = format_competitive_digest(digest)
    assert "Competitive Intelligence Digest" in md
    assert "Adapty" in md
    assert "Boundaries" in md
    assert "Public data only" in md


def test_competitors_registry():
    assert len(COMPETITORS) >= 3
    for key, comp in COMPETITORS.items():
        assert "name" in comp
        assert "pricing_url" in comp
        assert comp["pricing_url"].startswith("https://")


def test_boundaries_defined():
    assert "Public data only" in BOUNDARIES
    assert "No scraping behind authentication" in BOUNDARIES


def test_format_digest_empty():
    digest = CompetitiveDigest(
        week_of="2026-03-05",
        market_summary="No signals.",
        rc_positioning="Steady state.",
    )
    md = format_competitive_digest(digest)
    assert "No new signals" in md


def test_digest_has_action_items(mock_config):
    digest = generate_competitive_digest(mock_config)
    assert isinstance(digest.action_items, list)


def test_format_digest_with_multiple_signals():
    """Format handles multiple signals across competitors."""
    digest = CompetitiveDigest(
        week_of="2026-03-05",
        signals=[
            CompetitorSignal(
                competitor="Adapty", signal_type="pricing_snapshot",
                title="Adapty pricing", summary="MTR-based tiers",
                source_url="https://adapty.io/pricing/",
                relevance="Direct pricing comparison",
                so_what="Highlight RC's transparent pricing model",
                detected_at="2026-03-05T00:00:00Z",
            ),
            CompetitorSignal(
                competitor="Superwall", signal_type="blog_snapshot",
                title="Superwall blog update", summary="New paywall SDK release",
                source_url="https://superwall.com/blog",
                relevance="Feature parity check",
                so_what="Ensure RC Paywalls docs highlight differentiators",
                detected_at="2026-03-05T00:00:00Z",
            ),
        ],
        market_summary="2 signals from 2 competitors.",
        rc_positioning="MCP server differentiator.",
        action_items=["Compare pricing", "Update paywall docs"],
    )
    md = format_competitive_digest(digest)
    assert "Adapty" in md
    assert "Superwall" in md
    assert "Compare pricing" in md
