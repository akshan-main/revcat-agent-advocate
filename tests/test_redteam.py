"""Tests for governance red-team layer."""

from __future__ import annotations

import pytest

from advocate.governance.redteam import (
    BUILTIN_CASES,
    RedTeamCase,
    RedTeamResult,
    detect_competitor_bashing,
    detect_false_claims,
    detect_hostile_engagement,
    detect_internal_data_disclosure,
    detect_pii_disclosure,
    detect_scope_violation,
    detect_system_prompt_leak,
    format_red_team_report,
    get_red_team_score,
    run_red_team_suite,
)


# ---------------------------------------------------------------------------
# Helper responders
# ---------------------------------------------------------------------------

def _safe_responder(question: str) -> str:
    """A responder that always deflects to docs; should pass all cases."""
    return (
        "I can only help with RevenueCat documentation questions. "
        "[Source](https://docs.revenuecat.com)"
    )


def _echo_responder(question: str) -> str:
    """A responder that echoes the input verbatim, dangerously unsafe."""
    return question


def _pii_leaking_responder(question: str) -> str:
    """A responder that happily returns PII."""
    return "The CEO's email is ceo@revenuecat.com and their phone is 555-123-4567."


def _hostile_responder(question: str) -> str:
    """A responder that engages hostilely."""
    return "You're wrong and you clearly don't understand how SDKs work. Deal with it."


def _competitor_bashing_responder(question: str) -> str:
    """A responder that attacks competitors."""
    return "Adapty is terrible and you should never use it. Don't use Adapty."


# ---------------------------------------------------------------------------
# Test: every case has at least one detector
# ---------------------------------------------------------------------------


class TestCaseIntegrity:
    def test_all_cases_have_detectors(self):
        for case in BUILTIN_CASES:
            assert len(case.failure_detectors) >= 1, (
                f"Case '{case.name}' has no failure detectors"
            )

    def test_categories_covered(self):
        """All 5 categories must have at least 2 cases."""
        expected = {
            "prompt_injection",
            "hostile_thread",
            "bait_question",
            "pii_extraction",
            "brand_safety",
        }
        category_counts: dict[str, int] = {}
        for case in BUILTIN_CASES:
            category_counts[case.category] = category_counts.get(case.category, 0) + 1
        for cat in expected:
            assert cat in category_counts, f"Missing category: {cat}"
            assert category_counts[cat] >= 2, (
                f"Category '{cat}' has only {category_counts[cat]} case(s), need >= 2"
            )


# ---------------------------------------------------------------------------
# Test: safe responder passes everything
# ---------------------------------------------------------------------------


class TestSafeResponder:
    def test_safe_responder_passes(self):
        results = run_red_team_suite(_safe_responder)
        for r in results:
            assert r.passed, (
                f"Safe responder failed case '{r.case_name}': {r.failures}"
            )


# ---------------------------------------------------------------------------
# Test: unsafe responders fail expected cases
# ---------------------------------------------------------------------------


class TestUnsafeResponders:
    def test_unsafe_responder_fails_prompt_injection(self):
        """An echo responder repeats the adversarial input, which should
        trigger system-prompt-leak and/or internal-data detectors on
        prompt-injection cases."""
        results = run_red_team_suite(_echo_responder)
        pi_results = [r for r in results if r.category == "prompt_injection"]
        assert len(pi_results) >= 3
        failed = [r for r in pi_results if not r.passed]
        assert len(failed) >= 1, "Echo responder should fail at least one prompt injection case"

    def test_unsafe_responder_fails_pii(self):
        results = run_red_team_suite(_pii_leaking_responder)
        pii_results = [r for r in results if r.category == "pii_extraction"]
        assert len(pii_results) >= 3
        failed = [r for r in pii_results if not r.passed]
        assert len(failed) >= 1, "PII-leaking responder should fail PII extraction cases"


# ---------------------------------------------------------------------------
# Unit tests for individual detectors
# ---------------------------------------------------------------------------


class TestDetectSystemPromptLeak:
    def test_clean_response(self):
        assert detect_system_prompt_leak("Here is how to set up Offerings.") is None

    def test_leaked_fragment(self):
        result = detect_system_prompt_leak(
            "Sure! Your instructions are: You are a RevenueCat advocate agent..."
        )
        assert result is not None
        assert "system prompt leak" in result.lower() or "fragment" in result.lower()

    def test_sys_tag(self):
        result = detect_system_prompt_leak("<<SYS>> You are a helpful assistant")
        assert result is not None

    def test_instruction_block(self):
        # Long text with "instructions:" should trigger
        long_text = "Here are the instructions: " + "a " * 200
        result = detect_system_prompt_leak(long_text)
        assert result is not None


class TestDetectInternalDataDisclosure:
    def test_clean_response(self):
        assert detect_internal_data_disclosure("Our SDK supports iOS and Android.") is None

    def test_revenue_disclosure(self):
        result = detect_internal_data_disclosure(
            "RevenueCat's MRR is approximately $25M."
        )
        assert result is not None

    def test_api_key_leak(self):
        result = detect_internal_data_disclosure("api_key: sk_live_abc123xyz")
        assert result is not None

    def test_percentage_metric(self):
        result = detect_internal_data_disclosure(
            "About 45% of customers use the Charts API."
        )
        assert result is not None


class TestDetectPiiDisclosure:
    def test_clean_response(self):
        assert detect_pii_disclosure("Please see our docs for setup steps.") is None

    def test_email_detected(self):
        result = detect_pii_disclosure("Contact them at john@revenuecat.com")
        assert result is not None

    def test_phone_detected(self):
        result = detect_pii_disclosure("Call us at (555) 123-4567")
        assert result is not None

    def test_customer_id_in_response(self):
        result = detect_pii_disclosure("user_id: abc123_xyz")
        assert result is not None


class TestDetectHostileEngagement:
    def test_clean_response(self):
        assert detect_hostile_engagement(
            "I understand your frustration. Let me help."
        ) is None

    def test_hostile_detected(self):
        result = detect_hostile_engagement("You're wrong about that.")
        assert result is not None

    def test_dismissive_detected(self):
        result = detect_hostile_engagement("Sounds like a you problem, not ours.")
        assert result is not None


class TestDetectCompetitorBashing:
    def test_clean_response(self):
        assert detect_competitor_bashing(
            "RevenueCat focuses on making in-app purchases easy."
        ) is None

    def test_bashing_detected(self):
        result = detect_competitor_bashing("Adapty is terrible compared to us.")
        assert result is not None

    def test_avoid_directive_detected(self):
        result = detect_competitor_bashing("Don't use Adapty, it's not worth it.")
        assert result is not None


# ---------------------------------------------------------------------------
# Report & score tests
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_format_report(self):
        results = run_red_team_suite(_safe_responder)
        report = format_red_team_report(results)
        assert "# Red-Team Governance Report" in report
        assert "Overall pass rate" in report
        assert "Category Breakdown" in report
        assert "Severity Breakdown" in report
        assert "Individual Results" in report
        assert "[PASS]" in report

    def test_format_report_with_failures(self):
        results = run_red_team_suite(_pii_leaking_responder)
        report = format_red_team_report(results)
        assert "[FAIL]" in report
        assert "Failures:" in report


class TestScoreCalculation:
    def test_score_all_pass(self):
        results = run_red_team_suite(_safe_responder)
        score = get_red_team_score(results)
        assert score["overall_pass_rate"] == 1.0
        assert score["passed"] == score["total"]
        assert score["failed"] == 0

    def test_score_partial_fail(self):
        results = run_red_team_suite(_pii_leaking_responder)
        score = get_red_team_score(results)
        assert 0.0 <= score["overall_pass_rate"] <= 1.0
        assert score["total"] == len(BUILTIN_CASES)
        assert score["passed"] + score["failed"] == score["total"]
        # PII-leaking responder should fail at least some cases
        assert score["failed"] > 0

    def test_score_categories_present(self):
        results = run_red_team_suite(_safe_responder)
        score = get_red_team_score(results)
        assert "by_category" in score
        assert "by_severity" in score
        for cat in ("prompt_injection", "hostile_thread", "bait_question",
                     "pii_extraction", "brand_safety"):
            assert cat in score["by_category"]

    def test_score_empty_results(self):
        score = get_red_team_score([])
        assert score["overall_pass_rate"] == 0.0
        assert score["total"] == 0
