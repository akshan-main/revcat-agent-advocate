"""Content Linter: editorial quality enforcement, not vibes.

Every piece of content must pass automated quality checks before publishing:
- No filler intros ("In this article, we will...")
- Every factual claim requires a citation
- No hedging language presented as fact
- Code blocks must have a language tag
- Structure must follow the template contract
- Novelty check: don't repeat what's already published
"""
import re
from dataclasses import dataclass, field


@dataclass
class LintIssue:
    """A single linting issue found in content."""
    rule: str
    severity: str     # error, warning, info
    line: int | None
    message: str
    suggestion: str = ""


@dataclass
class LintResult:
    """Result of linting a content piece."""
    passed: bool
    issues: list[LintIssue] = field(default_factory=list)
    score: float = 0.0  # 0-100, higher is better
    word_count: int = 0
    citation_count: int = 0


# ── Filler Detection ───────────────────────────────────────────────────

FILLER_PATTERNS = [
    (r"^In this (?:article|tutorial|guide|post),?\s+(?:we will|we're going to|I will|you will)", "filler-intro"),
    (r"^(?:As you (?:may|might) know|It's no secret that|It goes without saying)", "filler-preamble"),
    (r"^(?:In today's (?:world|landscape|ecosystem)|In the (?:fast-paced|ever-changing))", "filler-cliche"),
    (r"(?:Without further ado|Let's dive (?:right )?in|Let's get started)", "filler-transition"),
    (r"(?:At the end of the day|When all is said and done|Last but not least)", "filler-cliche"),
    (r"^(?:Are you looking for|Have you ever wondered|Do you want to)", "filler-question"),
]


def _check_filler(content: str) -> list[LintIssue]:
    """Detect filler intros and cliches."""
    issues = []
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        for pattern, rule in FILLER_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                issues.append(LintIssue(
                    rule=rule,
                    severity="warning",
                    line=i,
                    message=f"Filler detected: '{stripped[:80]}...'",
                    suggestion="Start with the actual information. Delete this sentence and begin with the key point.",
                ))
    return issues


# ── Citation Enforcement ───────────────────────────────────────────────

FACTUAL_CLAIM_PATTERNS = [
    r"RevenueCat (?:supports?|provides?|offers?|includes?|has|uses?)\b",
    r"The (?:SDK|API|MCP|Charts|dashboard)\b.*(?:allows?|enables?|provides?|supports?)\b",
    r"You (?:can|should|must|need to)\b.*(?:RevenueCat|API|SDK|MCP)\b",
    r"(?:By default|Currently|As of)\b.*(?:RevenueCat|subscription|offering|entitlement)\b",
    r"\b(?:up to|at least|more than|over)\s+\d+\s+(?:tools?|endpoints?|metrics?|features?)\b",
]


def _check_citations(content: str) -> list[LintIssue]:
    """Ensure factual claims about RevenueCat have citations."""
    issues = []
    citation_pattern = r'\[(?:Source|[^\]]+)\]\(https?://[^)]+\)'
    lines = content.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("```"):
            continue

        for pattern in FACTUAL_CLAIM_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                # Check if this line or surrounding context has a citation
                context_start = max(0, i - 2)
                context_end = min(len(lines), i + 2)
                context = "\n".join(lines[context_start:context_end])
                if not re.search(citation_pattern, context):
                    issues.append(LintIssue(
                        rule="citation-required",
                        severity="error",
                        line=i,
                        message=f"Factual claim without citation: '{stripped[:100]}...'",
                        suggestion="Add [Source](url) citation from RevenueCat docs",
                    ))
                break  # One issue per line max

    return issues


# ── Hedging Language ───────────────────────────────────────────────────

HEDGING_PATTERNS = [
    (r"\bI think\b", "hedging-opinion"),
    (r"\bI believe\b", "hedging-opinion"),
    (r"\bprobably\b", "hedging-uncertainty"),
    (r"\bmaybe\b", "hedging-uncertainty"),
    (r"\bmight be\b", "hedging-uncertainty"),
    (r"\bcould be\b", "hedging-uncertainty"),
    (r"\bI'm not sure\b", "hedging-uncertainty"),
    (r"\bseems like\b", "hedging-vague"),
    (r"\bappears to\b", "hedging-vague"),
]


def _check_hedging(content: str) -> list[LintIssue]:
    """Detect hedging language used as factual statements."""
    issues = []
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):  # Skip blockquotes
            continue
        for pattern, rule in HEDGING_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                issues.append(LintIssue(
                    rule=rule,
                    severity="warning",
                    line=i,
                    message=f"Hedging language: '{stripped[:80]}...'",
                    suggestion="Either cite a source or explicitly say 'refer to the documentation'",
                ))
    return issues


# ── Code Block Quality ─────────────────────────────────────────────────

def _check_code_blocks(content: str) -> list[LintIssue]:
    """Ensure code blocks have language tags and aren't empty."""
    issues = []
    in_code_block = False
    code_block_start = 0
    code_block_lang = ""
    code_block_lines = 0

    for i, line in enumerate(content.splitlines(), 1):
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_block_start = i
                code_block_lang = line.strip()[3:].strip()
                code_block_lines = 0
                if not code_block_lang:
                    issues.append(LintIssue(
                        rule="code-no-language",
                        severity="warning",
                        line=i,
                        message="Code block without language tag",
                        suggestion="Add language tag: ```python, ```javascript, ```swift, etc.",
                    ))
            else:
                in_code_block = False
                if code_block_lines == 0:
                    issues.append(LintIssue(
                        rule="code-empty",
                        severity="error",
                        line=code_block_start,
                        message="Empty code block",
                        suggestion="Add actual code or remove the block",
                    ))
        elif in_code_block:
            if line.strip():
                code_block_lines += 1

    return issues


# ── Structure Checks ───────────────────────────────────────────────────

def _check_structure(content: str, content_type: str = "") -> list[LintIssue]:
    """Check content follows expected structure."""
    issues = []

    # Must have a title (H1)
    if not re.search(r'^# .+', content, re.MULTILINE):
        issues.append(LintIssue(
            rule="structure-no-title",
            severity="error",
            line=1,
            message="Content missing H1 title",
            suggestion="Add a descriptive # Title at the top",
        ))

    # Must have a Sources section
    if not re.search(r'^#{1,3}\s+Sources?\s*$', content, re.MULTILINE | re.IGNORECASE):
        issues.append(LintIssue(
            rule="structure-no-sources",
            severity="error",
            line=None,
            message="Content missing ## Sources section",
            suggestion="Add a ## Sources section at the end listing all cited documentation",
        ))

    # Must have at least 2 sections (H2)
    h2_count = len(re.findall(r'^## .+', content, re.MULTILINE))
    if h2_count < 2:
        issues.append(LintIssue(
            rule="structure-thin",
            severity="warning",
            line=None,
            message=f"Only {h2_count} sections; content may be too thin",
            suggestion="Add more sections to cover the topic thoroughly",
        ))

    return issues


# ── Novelty Check ──────────────────────────────────────────────────────

def _check_novelty(content: str, existing_slugs: list[str], existing_titles: list[str]) -> list[LintIssue]:
    """Check that content isn't duplicating existing pieces."""
    issues = []

    # Extract title from content
    title_match = re.search(r'^# (.+)', content, re.MULTILINE)
    if title_match:
        new_title = title_match.group(1).strip().lower()
        for existing in existing_titles:
            existing_lower = existing.lower()
            # Simple overlap check
            new_words = set(new_title.split())
            existing_words = set(existing_lower.split())
            if len(new_words) > 3 and len(existing_words) > 3:
                overlap = len(new_words & existing_words) / max(len(new_words), 1)
                if overlap > 0.7:
                    issues.append(LintIssue(
                        rule="novelty-duplicate",
                        severity="warning",
                        line=1,
                        message=f"Title very similar to existing: '{existing}'",
                        suggestion="Differentiate the angle or merge with existing content",
                    ))

    return issues


# ── Main Linter ────────────────────────────────────────────────────────

def lint_content(
    content: str,
    content_type: str = "",
    existing_titles: list[str] | None = None,
    existing_slugs: list[str] | None = None,
) -> LintResult:
    """Run all lint checks on a piece of content.

    Returns LintResult with pass/fail, issues, and a quality score.
    """
    issues = []

    issues.extend(_check_filler(content))
    issues.extend(_check_citations(content))
    issues.extend(_check_hedging(content))
    issues.extend(_check_code_blocks(content))
    issues.extend(_check_structure(content, content_type))

    if existing_titles or existing_slugs:
        issues.extend(_check_novelty(content, existing_slugs or [], existing_titles or []))

    # Count stats
    word_count = len(content.split())
    citation_pattern = r'\[(?:Source|[^\]]+)\]\(https?://[^)]+\)'
    citation_count = len(re.findall(citation_pattern, content))

    # Calculate score (100 = perfect)
    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    score = max(0, 100 - (error_count * 15) - (warning_count * 5))

    # Bonus for citations
    if citation_count >= 3:
        score = min(100, score + 5)

    passed = error_count == 0

    return LintResult(
        passed=passed,
        issues=issues,
        score=score,
        word_count=word_count,
        citation_count=citation_count,
    )


def format_lint_result(result: LintResult) -> str:
    """Format lint result as human-readable report."""
    status = "PASS" if result.passed else "FAIL"
    lines = [
        f"## Content Lint: {status} (Score: {result.score:.0f}/100)",
        f"Words: {result.word_count} | Citations: {result.citation_count}",
        "",
    ]

    if not result.issues:
        lines.append("No issues found.")
        return "\n".join(lines)

    # Group by severity
    for severity in ("error", "warning", "info"):
        sev_issues = [i for i in result.issues if i.severity == severity]
        if sev_issues:
            lines.append(f"### {severity.upper()}S ({len(sev_issues)})")
            for issue in sev_issues:
                loc = f"L{issue.line}" if issue.line else "--"
                lines.append(f"- [{loc}] `{issue.rule}`: {issue.message}")
                if issue.suggestion:
                    lines.append(f"  Fix: {issue.suggestion}")
            lines.append("")

    return "\n".join(lines)
