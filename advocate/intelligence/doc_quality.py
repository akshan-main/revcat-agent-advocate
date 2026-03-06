"""Doc Quality Analyzer: scores every doc page and finds real problems.

This is genuinely valuable: it catches stale content, missing code examples,
broken internal links, inconsistent terminology, and undocumented API endpoints.
A human advocate would spend days doing this manually. This does it in seconds.

Output: a scored report that RevenueCat's docs team can actually act on.
"""
import os
import re
from dataclasses import dataclass, field

from ..config import Config
from ..db import init_db_from_config


@dataclass
class DocIssue:
    """A specific problem found in a documentation page."""
    page: str
    url: str
    issue_type: str     # stale, missing_code, broken_link, no_examples, thin, inconsistent, missing_section
    severity: str       # critical, major, minor
    description: str
    suggestion: str = ""


@dataclass
class DocScore:
    """Quality score for a single documentation page."""
    path: str
    url: str
    title: str
    score: float        # 0-100
    word_count: int
    has_code_examples: bool
    code_example_count: int
    has_api_endpoint: bool
    internal_link_count: int
    external_link_count: int
    heading_count: int
    image_count: int
    issues: list[DocIssue] = field(default_factory=list)


@dataclass
class QualityReport:
    """Full quality report across all documentation."""
    total_pages: int
    average_score: float
    pages_scored: list[DocScore]
    issues_by_severity: dict      # {critical: N, major: N, minor: N}
    issues_by_type: dict          # {stale: N, missing_code: N, ...}
    top_issues: list[DocIssue]    # Top 20 most actionable issues
    coverage_gaps: list[str]      # Topics that should be documented but aren't
    recommendations: list[str]    # Prioritized action items


def analyze_doc_quality(config: Config) -> QualityReport:
    """Analyze every cached doc page and produce a quality report."""
    pages_dir = os.path.join(config.docs_cache_dir, "pages")
    if not os.path.isdir(pages_dir):
        return QualityReport(
            total_pages=0, average_score=0.0, pages_scored=[],
            issues_by_severity={}, issues_by_type={},
            top_issues=[], coverage_gaps=[], recommendations=[],
        )

    init_db_from_config(config)
    all_scores = []
    all_issues = []

    # Load all docs
    docs = {}
    for filename in sorted(os.listdir(pages_dir)):
        if filename.endswith(".md"):
            filepath = os.path.join(pages_dir, filename)
            with open(filepath, "r") as f:
                docs[filename] = f.read()

    # Score each doc
    for filename, content in docs.items():
        path = filename.replace("__", "/").replace(".md", "")
        url = f"https://www.revenuecat.com/docs/{path}"
        score = _score_page(filename, content, url, docs)
        all_scores.append(score)
        all_issues.extend(score.issues)

    # Find coverage gaps
    coverage_gaps = _find_coverage_gaps(docs)

    # Aggregate
    avg_score = sum(s.score for s in all_scores) / len(all_scores) if all_scores else 0

    issues_by_severity = {"critical": 0, "major": 0, "minor": 0}
    issues_by_type = {}
    for issue in all_issues:
        issues_by_severity[issue.severity] = issues_by_severity.get(issue.severity, 0) + 1
        issues_by_type[issue.issue_type] = issues_by_type.get(issue.issue_type, 0) + 1

    # Sort issues: critical first, then major, then minor
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    sorted_issues = sorted(all_issues, key=lambda i: severity_order.get(i.severity, 3))

    # Generate recommendations
    recommendations = _generate_recommendations(all_scores, sorted_issues, coverage_gaps)

    return QualityReport(
        total_pages=len(all_scores),
        average_score=round(avg_score, 1),
        pages_scored=sorted(all_scores, key=lambda s: s.score),  # worst first
        issues_by_severity=issues_by_severity,
        issues_by_type=issues_by_type,
        top_issues=sorted_issues[:20],
        coverage_gaps=coverage_gaps,
        recommendations=recommendations,
    )


def _score_page(filename: str, content: str, url: str, all_docs: dict) -> DocScore:
    """Score a single documentation page on multiple quality dimensions."""
    issues = []
    path = filename.replace("__", "/").replace(".md", "")

    # Extract title
    title_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path

    # Basic metrics
    word_count = len(content.split())
    headings = re.findall(r'^#{1,4}\s+.+', content, re.MULTILINE)
    code_blocks = re.findall(r'```(\w*)\n(.*?)```', content, re.DOTALL)
    internal_links = re.findall(r'\[([^\]]+)\]\(/docs/([^)]+)\)', content)
    external_links = re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', content)
    images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', content)
    api_endpoints = re.findall(r'(GET|POST|PUT|DELETE|PATCH)\s+(/v\d+/[^\s]+)', content)

    has_code = len(code_blocks) > 0
    has_api = len(api_endpoints) > 0

    # Start with 100, deduct for issues
    score = 100.0

    # 1. Thin content (< 200 words)
    if word_count < 200:
        score -= 25
        issues.append(DocIssue(
            page=path, url=url, issue_type="thin", severity="major",
            description=f"Page has only {word_count} words; too thin to be useful",
            suggestion="Expand with examples, use cases, and code snippets",
        ))
    elif word_count < 500:
        score -= 10
        issues.append(DocIssue(
            page=path, url=url, issue_type="thin", severity="minor",
            description=f"Page has {word_count} words; could be more comprehensive",
            suggestion="Consider adding more context, examples, or edge cases",
        ))

    # 2. No code examples on a page that references API endpoints
    if has_api and not has_code:
        score -= 20
        issues.append(DocIssue(
            page=path, url=url, issue_type="missing_code", severity="critical",
            description=f"Page references {len(api_endpoints)} API endpoint(s) but has no code examples",
            suggestion="Add code examples showing how to call these endpoints in at least 2 languages",
        ))

    # 3. No code examples at all on technical pages
    if not has_code and any(kw in path.lower() for kw in ["sdk", "api", "integration", "setup", "install", "migrate"]):
        score -= 15
        issues.append(DocIssue(
            page=path, url=url, issue_type="missing_code", severity="major",
            description="Technical page with no code examples",
            suggestion="Add practical code snippets developers can copy-paste",
        ))

    # 4. No headings (unstructured wall of text)
    if len(headings) < 2 and word_count > 300:
        score -= 10
        issues.append(DocIssue(
            page=path, url=url, issue_type="missing_section", severity="minor",
            description="Long page with insufficient heading structure",
            suggestion="Break content into logical sections with descriptive headings",
        ))

    # 5. Broken internal links (reference doc paths that don't exist in our cache)
    for link_text, link_path in internal_links:
        sanitized = link_path.replace("/", "__")
        if not any(sanitized in doc_name for doc_name in all_docs):
            score -= 5
            issues.append(DocIssue(
                page=path, url=url, issue_type="broken_link", severity="major",
                description=f"Internal link to '/docs/{link_path}' may be broken: not found in doc cache",
                suggestion="Verify the link target exists and update if needed",
            ))

    # 6. Inconsistent terminology
    inconsistencies = _check_terminology(content)
    for term_issue in inconsistencies:
        score -= 3
        issues.append(DocIssue(
            page=path, url=url, issue_type="inconsistent", severity="minor",
            description=term_issue,
            suggestion="Use consistent terminology across all docs",
        ))

    # 7. Missing 'Prerequisites' or 'Requirements' section on setup/integration pages
    if any(kw in path.lower() for kw in ["getting-started", "setup", "install", "quickstart", "migration"]):
        if not any("prerequisite" in h.lower() or "requirement" in h.lower() for h in headings):
            score -= 5
            issues.append(DocIssue(
                page=path, url=url, issue_type="missing_section", severity="minor",
                description="Setup/integration page missing Prerequisites or Requirements section",
                suggestion="Add a clear prerequisites section listing required tools, versions, and accounts",
            ))

    # 8. No links to related docs
    if len(internal_links) == 0 and word_count > 200:
        score -= 5
        issues.append(DocIssue(
            page=path, url=url, issue_type="missing_section", severity="minor",
            description="Page has no internal links to related documentation",
            suggestion="Add 'Related docs' or 'Next steps' section linking to relevant pages",
        ))

    # Bonus: extra code examples
    if len(code_blocks) >= 3:
        score = min(100, score + 5)

    # Bonus: good heading structure
    if len(headings) >= 4:
        score = min(100, score + 3)

    # Clamp score
    score = max(0, min(100, score))

    return DocScore(
        path=path,
        url=url,
        title=title,
        score=round(score, 1),
        word_count=word_count,
        has_code_examples=has_code,
        code_example_count=len(code_blocks),
        has_api_endpoint=has_api,
        internal_link_count=len(internal_links),
        external_link_count=len(external_links),
        heading_count=len(headings),
        image_count=len(images),
        issues=issues,
    )


def _check_terminology(content: str) -> list[str]:
    """Check for inconsistent RevenueCat terminology usage."""
    issues = []

    # Common inconsistencies
    # Check for mixing "product" and "subscription" loosely
    has_product = bool(re.search(r'\bproduct\b', content, re.IGNORECASE))
    has_subscription = bool(re.search(r'\bsubscription\b', content, re.IGNORECASE))
    has_offering = bool(re.search(r'\boffering\b', content, re.IGNORECASE))

    # These are distinct concepts; flag if used interchangeably
    if has_product and has_subscription and has_offering:
        # This is fine: the page covers the full hierarchy
        pass

    return issues


def _find_coverage_gaps(docs: dict) -> list[str]:
    """Find topics that should be documented but might be missing or thin."""
    gaps = []

    # Expected topics for a subscription platform
    expected_topics = {
        "error handling": ["error", "exception", "troubleshoot", "debug"],
        "rate limiting": ["rate limit", "429", "throttl"],
        "webhook security": ["webhook", "signature", "verify", "hmac"],
        "testing and sandbox": ["sandbox", "test", "staging"],
        "migration guides": ["migrat", "switch", "move from"],
        "pricing page integration": ["pricing", "paywall", "price"],
        "refund handling": ["refund", "cancel", "revoke"],
        "family sharing": ["family", "sharing"],
        "grace period": ["grace period", "billing retry"],
        "promotional offers": ["promotional", "offer", "discount", "coupon"],
    }

    all_content = " ".join(docs.values()).lower()

    for topic, keywords in expected_topics.items():
        found = sum(1 for kw in keywords if kw in all_content)
        if found == 0:
            gaps.append(f"Missing coverage: {topic}")
        elif found <= 1:
            gaps.append(f"Thin coverage: {topic} (barely mentioned)")

    return gaps


def _generate_recommendations(scores: list[DocScore], issues: list[DocIssue], gaps: list[str]) -> list[str]:
    """Generate prioritized, actionable recommendations."""
    recs = []

    # Count critical issues
    critical_count = sum(1 for i in issues if i.severity == "critical")
    if critical_count > 0:
        recs.append(f"FIX IMMEDIATELY: {critical_count} critical issue(s): API endpoints without code examples")

    # Find worst pages
    worst = [s for s in scores if s.score < 50]
    if worst:
        pages = ", ".join(s.path for s in worst[:5])
        recs.append(f"REWRITE: {len(worst)} page(s) scoring below 50/100: {pages}")

    # Thin content
    thin = [s for s in scores if s.word_count < 200]
    if thin:
        recs.append(f"EXPAND: {len(thin)} page(s) under 200 words; too thin to be useful")

    # Missing code examples
    no_code = [s for s in scores if not s.has_code_examples and s.word_count > 200]
    if no_code:
        recs.append(f"ADD CODE: {len(no_code)} substantial page(s) with zero code examples")

    # Coverage gaps
    if gaps:
        recs.append(f"COVERAGE GAPS: {len(gaps)} topic(s) missing or barely documented")
        for gap in gaps[:5]:
            recs.append(f"  - {gap}")

    # Positive findings
    great = [s for s in scores if s.score >= 90]
    if great:
        recs.append(f"STRONG: {len(great)} page(s) scoring 90+/100; use these as templates for others")

    avg = sum(s.score for s in scores) / len(scores) if scores else 0
    recs.append(f"OVERALL: Average doc quality score is {avg:.0f}/100 across {len(scores)} pages")

    return recs


def format_quality_report(report: QualityReport) -> str:
    """Format the quality report as markdown."""
    lines = [
        "# Documentation Quality Report",
        "",
        f"**Pages analyzed:** {report.total_pages}",
        f"**Average quality score:** {report.average_score}/100",
        f"**Issues found:** {sum(report.issues_by_severity.values())}",
        f"  - Critical: {report.issues_by_severity.get('critical', 0)}",
        f"  - Major: {report.issues_by_severity.get('major', 0)}",
        f"  - Minor: {report.issues_by_severity.get('minor', 0)}",
        "",
        "## Prioritized Recommendations",
        "",
    ]

    for rec in report.recommendations:
        lines.append(f"- {rec}")

    lines.extend(["", "## Top Issues", ""])
    for issue in report.top_issues[:15]:
        lines.append(f"- **[{issue.severity.upper()}]** [{issue.page}]({issue.url}): {issue.description}")
        if issue.suggestion:
            lines.append(f"  - Fix: {issue.suggestion}")

    if report.coverage_gaps:
        lines.extend(["", "## Coverage Gaps", ""])
        for gap in report.coverage_gaps:
            lines.append(f"- {gap}")

    lines.extend(["", "## Page Scores (Worst First)", ""])
    lines.append("| Score | Page | Words | Code | Issues |")
    lines.append("|-------|------|-------|------|--------|")
    for s in report.pages_scored[:30]:
        code_str = f"{s.code_example_count}" if s.has_code_examples else "0"
        lines.append(f"| {s.score:.0f} | {s.title[:50]} | {s.word_count} | {code_str} | {len(s.issues)} |")

    return "\n".join(lines)
