"""Tests for the policy engine: triage, quality gates, brand safety."""
from advocate.distribution.policy import (
    triage,
    check_quality,
    triage_batch,
    TriageDecision,
    QualityGate,
)


# ── Triage Tests ──────────────────────────────────────────────────────

def test_triage_spam():
    result = triage("Buy followers and check my app!")
    assert result.decision == TriageDecision.SKIP
    assert result.confidence > 0.8


def test_triage_private():
    result = triage("My account isn't showing the right subscription. My API key is sk_...")
    assert result.decision == TriageDecision.PRIVATE


def test_triage_escalate_pricing():
    result = triage("What about the price increase for enterprise plans?")
    assert result.decision == TriageDecision.ESCALATE


def test_triage_escalate_bug():
    result = triage("I'm seeing a crash and exception with a stack trace in the SDK")
    assert result.decision == TriageDecision.ESCALATE


def test_triage_reply_now():
    result = triage("How do I set up RevenueCat offerings for my paywall?")
    assert result.decision == TriageDecision.REPLY_NOW


def test_triage_reply_later():
    result = triage("RevenueCat SDK seems interesting")
    assert result.decision == TriageDecision.REPLY_LATER


def test_triage_skip_already_answered():
    result = triage("How do I configure webhooks?", context={"existing_replies": 5})
    assert result.decision == TriageDecision.SKIP
    assert "already_answered" in result.reason


def test_triage_skip_irrelevant():
    result = triage("What's the weather like today?")
    assert result.decision == TriageDecision.SKIP


# ── Quality Gate Tests ────────────────────────────────────────────────

def test_quality_pass():
    response = (
        "RevenueCat's Charts API provides access to MRR, churn, and LTV metrics. "
        "You can query the API using Bearer authentication with your secret key. "
        "The data is based on production receipt snapshots. "
        "[Source](https://docs.revenuecat.com/charts)"
    )
    result = check_quality(response)
    assert result.passed
    assert result.gate == QualityGate.PASS


def test_quality_fail_no_citations():
    response = (
        "RevenueCat provides access to various subscription metrics. "
        "You can view MRR, churn, and other data through the dashboard. "
        "The Charts API also supports programmatic access."
    )
    result = check_quality(response)
    assert not result.passed
    assert result.gate == QualityGate.FAIL_NO_CITATIONS


def test_quality_fail_too_short():
    result = check_quality("Just use the SDK.")
    assert not result.passed
    assert any("too short" in i for i in result.issues)


def test_quality_fail_hedging():
    response = (
        "I think RevenueCat probably supports this feature. "
        "Maybe you should check the documentation. "
        "[Source](https://docs.revenuecat.com)"
    )
    result = check_quality(response)
    assert any("Hedging" in i for i in result.issues)


def test_quality_fail_promotional():
    response = (
        "RevenueCat is the best platform for subscriptions. "
        "It's superior to all alternatives. "
        "You should switch to RevenueCat immediately because it's better than everything else. "
        "[Source](https://docs.revenuecat.com)"
    )
    result = check_quality(response)
    assert any("promotional" in i for i in result.issues)


def test_quality_fail_repeats_question():
    question = "How do I set up RevenueCat offerings for my app?"
    response = "How do I set up RevenueCat offerings for my app? Good question."
    result = check_quality(response, question=question)
    assert any("repeat" in i for i in result.issues)


# ── Batch Triage Tests ────────────────────────────────────────────────

def test_triage_batch_sorting():
    questions = [
        {"text": "What's the weather?"},  # SKIP
        {"text": "How do I configure RevenueCat offerings?"},  # REPLY_NOW
        {"text": "My account has a billing issue"},  # PRIVATE
    ]
    results = triage_batch(questions)
    # REPLY_NOW should be first
    assert results[0][1].decision == TriageDecision.REPLY_NOW


def test_triage_batch_with_context():
    questions = [
        {"text": "How does the SDK work?", "reply_count": 5},  # SKIP (already answered)
        {"text": "How does the SDK work?", "reply_count": 0},  # REPLY_NOW
    ]
    results = triage_batch(questions)
    decisions = [r[1].decision for r in results]
    assert TriageDecision.REPLY_NOW in decisions
    assert TriageDecision.SKIP in decisions
