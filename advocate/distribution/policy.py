"""Policy Engine: brand safety, triage, and quality gates.

A high-output agent that posts mediocre replies is a liability.
This module enforces quality before anything goes out:

- Triage classifier: reply now vs later vs never vs escalate
- Meaningful interaction definition (enforced, not vibes)
- Hard caps and cooling-off to prevent bursty behavior
- Quality gates: no low-effort replies, no uncited facts, no uncertainty-as-fact
"""
import re
from dataclasses import dataclass
from enum import Enum


class TriageDecision(str, Enum):
    REPLY_NOW = "reply_now"          # High confidence, clear answer in docs
    REPLY_LATER = "reply_later"      # Needs research or more context
    ESCALATE = "escalate"            # Needs human judgment (pricing, account issues, bugs)
    SKIP = "skip"                    # Not relevant, spam, or duplicate
    PRIVATE = "private"              # Should be handled in private (account details, PII)


class QualityGate(str, Enum):
    PASS = "pass"
    FAIL_NO_CITATIONS = "fail_no_citations"
    FAIL_LOW_EFFORT = "fail_low_effort"
    FAIL_UNCERTAINTY = "fail_uncertainty_as_fact"
    FAIL_REPEATED = "fail_repeated_user"
    FAIL_TOO_LONG = "fail_too_long"
    FAIL_TOO_SHORT = "fail_too_short"
    FAIL_PROMOTIONAL = "fail_too_promotional"


@dataclass
class TriageResult:
    decision: TriageDecision
    confidence: float      # 0-1
    reason: str
    priority: int          # 1=urgent, 2=normal, 3=low


@dataclass
class QualityResult:
    gate: QualityGate
    passed: bool
    issues: list[str]
    suggestions: list[str]


# ── Meaningful Interaction Definition ───────────────────────────────────

MEANINGFUL_INTERACTION_CRITERIA = """
A "meaningful interaction" MUST meet ALL of these:
1. Directly answers the question asked (not tangential)
2. Contains at least one citation to official documentation
3. Provides actionable next steps (not just "check the docs")
4. Is written in clear, developer-friendly language
5. Does not repeat the question back as padding

An interaction is NOT meaningful if it:
- Is a generic "have you tried X?" without specifics
- Links to docs without explaining the relevant part
- Contains hedging language ("I think", "maybe", "probably") for factual claims
- Is shorter than 50 words (likely too vague to be useful)
- Is longer than 500 words (likely too verbose for the context)
"""


# ── Triage Classifier ──────────────────────────────────────────────────

def triage(question: str, context: dict | None = None) -> TriageResult:
    """Classify an incoming question/issue for response priority.

    context can include: channel, author, is_repeat, existing_replies, etc.
    """
    context = context or {}
    text_lower = question.lower()

    # SKIP: spam, self-promotion, unrelated
    skip_signals = ["buy followers", "check my app", "hire me", "dm me", "subscribe to"]
    if any(s in text_lower for s in skip_signals):
        return TriageResult(TriageDecision.SKIP, 0.9, "spam_or_promotion", 3)

    # SKIP: already has good answers
    existing_replies = context.get("existing_replies", 0)
    if existing_replies >= 3:
        return TriageResult(TriageDecision.SKIP, 0.7, "already_answered", 3)

    # PRIVATE: account-specific or PII
    private_signals = ["my account", "my subscription", "customer id", "app user id",
                       "receipt", "my api key", "my project", "billing"]
    if any(s in text_lower for s in private_signals):
        return TriageResult(TriageDecision.PRIVATE, 0.8, "contains_account_specific_info", 2)

    # ESCALATE: pricing, bugs, security
    escalate_signals = ["pricing", "price increase", "enterprise", "security vulnerability",
                        "data breach", "legal", "compliance", "gdpr", "lawsuit"]
    if any(s in text_lower for s in escalate_signals):
        return TriageResult(TriageDecision.ESCALATE, 0.85, "needs_human_judgment", 1)

    # ESCALATE: bug reports with crash/error
    bug_signals = ["crash", "exception", "stack trace", "bug report", "regression", "broke"]
    if sum(1 for s in bug_signals if s in text_lower) >= 2:
        return TriageResult(TriageDecision.ESCALATE, 0.75, "likely_bug_report", 1)

    # REPLY_NOW: clear technical question about RevenueCat
    rc_signals = ["revenuecat", "purchases", "offering", "entitlement", "paywall",
                  "subscription", "mcp", "charts api", "webhook", "sdk"]
    question_signals = ["how", "what", "why", "when", "where", "does", "can", "is it", "?"]

    rc_relevance = sum(1 for s in rc_signals if s in text_lower)
    is_question = any(s in text_lower for s in question_signals)

    if rc_relevance >= 1 and is_question:
        return TriageResult(TriageDecision.REPLY_NOW, 0.8, "relevant_rc_question", 2)

    # REPLY_LATER: somewhat relevant but needs more context
    if rc_relevance >= 1:
        return TriageResult(TriageDecision.REPLY_LATER, 0.6, "relevant_but_unclear", 3)

    # Default: skip if not clearly relevant
    return TriageResult(TriageDecision.SKIP, 0.5, "not_clearly_relevant", 3)


# ── Quality Gates ──────────────────────────────────────────────────────

def check_quality(response: str, question: str = "", channel: str = "") -> QualityResult:
    """Run quality gates on a draft response before posting.

    Returns QualityResult with pass/fail and specific issues.
    """
    issues = []
    suggestions = []

    # Gate 1: Must have citations (for factual responses)
    citation_pattern = r'\[(?:Source|[^\]]+)\]\(https?://[^)]+\)'
    citations = re.findall(citation_pattern, response)
    if len(citations) == 0:
        issues.append("No citations found; every factual claim needs a source")
        suggestions.append("Add [Source](url) citations from RevenueCat docs")

    # Gate 2: Not too short (low effort)
    word_count = len(response.split())
    if word_count < 30:
        issues.append(f"Response too short ({word_count} words); likely not useful")
        suggestions.append("Expand with specific details and examples")

    # Gate 3: Not too long (verbose)
    max_words = 500 if channel in ("github_issue", "github_discussion", "reddit") else 280
    if word_count > max_words and channel == "twitter":
        issues.append(f"Response too long for {channel} ({word_count} words)")
        suggestions.append(f"Trim to under {max_words} words for this channel")

    # Gate 4: No uncertainty phrased as fact
    uncertainty_patterns = [
        r'\b(I think|I believe|probably|maybe|might be|could be|I\'m not sure)\b.*\.',
    ]
    for pattern in uncertainty_patterns:
        matches = re.findall(pattern, response, re.IGNORECASE)
        if matches:
            issues.append(f"Hedging language used as factual statement: '{matches[0]}'")
            suggestions.append("Either cite the source or explicitly say 'refer to the docs'")

    # Gate 5: Not just repeating the question
    if question:
        question_words = set(question.lower().split())
        response_words = set(response.lower().split()[:30])
        overlap = len(question_words & response_words) / max(len(question_words), 1)
        if overlap > 0.7 and word_count < 80:
            issues.append("Response appears to just repeat the question")
            suggestions.append("Add specific, actionable information")

    # Gate 6: Not too promotional
    promo_patterns = ["best platform", "superior to", "switch to revenuecat",
                      "you should use revenuecat", "better than"]
    promo_count = sum(1 for p in promo_patterns if p in response.lower())
    if promo_count >= 2:
        issues.append("Response sounds too promotional")
        suggestions.append("Focus on answering the question, not selling")

    # Determine overall result
    if not issues:
        return QualityResult(QualityGate.PASS, True, [], [])

    # Find the most severe issue
    if any("No citations" in i for i in issues):
        gate = QualityGate.FAIL_NO_CITATIONS
    elif any("too short" in i for i in issues):
        gate = QualityGate.FAIL_LOW_EFFORT
    elif any("Hedging" in i for i in issues):
        gate = QualityGate.FAIL_UNCERTAINTY
    elif any("promotional" in i for i in issues):
        gate = QualityGate.FAIL_PROMOTIONAL
    elif any("too long" in i for i in issues):
        gate = QualityGate.FAIL_TOO_LONG
    else:
        gate = QualityGate.FAIL_LOW_EFFORT

    return QualityResult(gate, False, issues, suggestions)


# ── Batch Triage ───────────────────────────────────────────────────────

def triage_batch(questions: list[dict]) -> list[tuple[dict, TriageResult]]:
    """Triage a batch of questions. Returns sorted by priority."""
    results = []
    for q in questions:
        text = q.get("question", q.get("text", q.get("title", "")))
        context = {
            "channel": q.get("channel", ""),
            "author": q.get("author", ""),
            "existing_replies": q.get("reply_count", 0),
        }
        result = triage(text, context)
        results.append((q, result))

    # Sort: reply_now first, then reply_later, skip escalate/private/skip
    priority_order = {
        TriageDecision.REPLY_NOW: 0,
        TriageDecision.REPLY_LATER: 1,
        TriageDecision.ESCALATE: 2,
        TriageDecision.PRIVATE: 3,
        TriageDecision.SKIP: 4,
    }
    results.sort(key=lambda x: (priority_order.get(x[1].decision, 5), x[1].priority))
    return results
