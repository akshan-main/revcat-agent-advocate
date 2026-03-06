"""Tests for the content linter: editorial quality enforcement."""
from advocate.content.linter import (
    lint_content,
    format_lint_result,
    _check_filler,
    _check_citations,
    _check_hedging,
    _check_code_blocks,
    _check_structure,
    _check_novelty,
    LintResult,
)


def test_filler_detection():
    issues = _check_filler("In this article, we will explore subscriptions.")
    assert len(issues) > 0
    assert any(i.rule == "filler-intro" for i in issues)


def test_filler_clean():
    issues = _check_filler("RevenueCat Charts API provides real-time metrics.")
    assert len(issues) == 0


def test_citation_required_for_factual_claim():
    text = "RevenueCat supports 26 MCP tools for AI agents."
    issues = _check_citations(text)
    assert len(issues) > 0
    assert any(i.rule == "citation-required" for i in issues)


def test_citation_satisfied():
    text = "RevenueCat supports 26 MCP tools [Source](https://docs.revenuecat.com/mcp)."
    issues = _check_citations(text)
    assert len(issues) == 0


def test_hedging_detection():
    issues = _check_hedging("I think RevenueCat might support this feature.")
    assert len(issues) > 0


def test_hedging_clean():
    issues = _check_hedging("RevenueCat supports this feature [Source](https://docs.rc.com).")
    assert len(issues) == 0


def test_code_block_no_language():
    content = "```\nprint('hello')\n```"
    issues = _check_code_blocks(content)
    assert any(i.rule == "code-no-language" for i in issues)


def test_code_block_with_language():
    content = "```python\nprint('hello')\n```"
    issues = _check_code_blocks(content)
    assert not any(i.rule == "code-no-language" for i in issues)


def test_code_block_empty():
    content = "```python\n```"
    issues = _check_code_blocks(content)
    assert any(i.rule == "code-empty" for i in issues)


def test_structure_no_title():
    issues = _check_structure("Just some text without a title.")
    assert any(i.rule == "structure-no-title" for i in issues)


def test_structure_no_sources():
    content = "# Title\n\nSome content.\n\n## Section\n\nMore content."
    issues = _check_structure(content)
    assert any(i.rule == "structure-no-sources" for i in issues)


def test_structure_complete():
    content = "# Title\n\n## Section 1\n\nContent.\n\n## Section 2\n\nMore.\n\n## Sources\n\nLinks."
    issues = _check_structure(content)
    assert not any(i.rule == "structure-no-title" for i in issues)
    assert not any(i.rule == "structure-no-sources" for i in issues)


def test_novelty_duplicate():
    issues = _check_novelty(
        "# Using RevenueCat Charts API for Agent Dashboards",
        existing_slugs=[],
        existing_titles=["Using RevenueCat Charts API for Agent Dashboards"],
    )
    assert any(i.rule == "novelty-duplicate" for i in issues)


def test_novelty_unique():
    issues = _check_novelty(
        "# MCP Server Integration Guide",
        existing_slugs=[],
        existing_titles=["Charts API Tutorial"],
    )
    assert len(issues) == 0


def test_lint_content_pass():
    content = """# RevenueCat Charts API Guide

## Introduction

The Charts API provides access to MRR and churn data [Source](https://docs.revenuecat.com/charts).

## Using the API

```python
import requests
response = requests.get("https://api.revenuecat.com/v2/charts/mrr")
```

The API returns JSON data with daily resolution [Source](https://docs.revenuecat.com/api).

## Sources

- [Charts](https://docs.revenuecat.com/charts)
- [API](https://docs.revenuecat.com/api)
"""
    result = lint_content(content)
    assert result.word_count > 0
    assert result.citation_count >= 2
    assert result.score > 0


def test_lint_content_fail_no_sources():
    content = "# Title\n\nJust text without citations or structure."
    result = lint_content(content)
    assert not result.passed
    assert any(i.rule == "structure-no-sources" for i in result.issues)


def test_format_lint_result():
    result = LintResult(passed=True, issues=[], score=95, word_count=200, citation_count=3)
    md = format_lint_result(result)
    assert "PASS" in md
    assert "95" in md


def test_format_lint_result_with_issues():
    from advocate.content.linter import LintIssue
    result = LintResult(
        passed=False,
        issues=[LintIssue(rule="test", severity="error", line=5, message="Test issue")],
        score=50, word_count=100, citation_count=0,
    )
    md = format_lint_result(result)
    assert "FAIL" in md
    assert "Test issue" in md
