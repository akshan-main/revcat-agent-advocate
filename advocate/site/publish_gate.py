"""Publish gate — blocks deploy if the application letter has banned phrases
or overclaims.

Checks only the letter (not the whole site). Returns a structured GateResult
so the CLI can block or proceed.
"""

import re
from dataclasses import dataclass, field

from ..db import count_rows, query_rows


# Phrases that should NEVER appear in the application letter
BANNED_PHRASES = [
    "not a pitch deck",
    "not a chatbot",
    "not a cover letter",
    "not a résumé",
    "not a pipeline",
    "API-first by nature",
    "you're not hiring a promise",
    "I am that audience",
    "no competitor offers",
    "complete subscription management",
    "the decision is effectively made",
]

# Patterns that indicate overclaims in the letter
BANNED_PATTERNS = [
    (r"every\s+(?:single\s+)?(?:action|command|operation)\s+(?:is|gets?|creates?)\s+(?:logged|recorded|hashed|a\s+row)",
     "overclaim: not every action is logged"),
    (r"zero\s+hallucination",
     "overclaim: can't guarantee zero hallucination"),
    (r"(?:I\s+am\s+not|I'm\s+not)\s+(?:a|an)\s+(?:chatbot|bot|resume|pitch|cover letter|pipeline|human|person|replacement)\b",
     "overclaim: avoid 'I am not X' constructions"),
    (r"no\s+competitor\s+(?:matches|offers|can|has|provides)",
     "overclaim: absolute competitive claims are unverifiable"),
    (r"\(Source\)",
     "broken source: (Source) placeholder instead of a real URL"),
    (r"no\s+human\s+review",
     "self-undermining: reframe as operator-gated publishing"),
]


@dataclass
class GateViolation:
    file: str
    line: int
    phrase: str
    reason: str


@dataclass
class GateResult:
    passed: bool
    violations: list[GateViolation] = field(default_factory=list)
    chain_valid: bool = True
    summary: str = ""


def _get_letter_body(db_conn) -> str:
    """Get the application letter body from the DB."""
    content = query_rows(db_conn, "content_pieces", where={"slug": "application-letter"})
    if content:
        return content[0].get("body_md", "")
    return ""


def check_banned_phrases(db_conn) -> list[GateViolation]:
    """Check the application letter for banned phrases and patterns."""
    violations = []
    body = _get_letter_body(db_conn)
    if not body:
        return violations

    lines = body.split("\n")
    for i, line in enumerate(lines, 1):
        line_lower = line.lower()
        for phrase in BANNED_PHRASES:
            if phrase.lower() in line_lower:
                violations.append(GateViolation(
                    file="application-letter",
                    line=i,
                    phrase=phrase,
                    reason=f"Banned phrase found: '{phrase}'",
                ))
        for pattern, reason in BANNED_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                violations.append(GateViolation(
                    file="application-letter",
                    line=i,
                    phrase=re.search(pattern, line, re.IGNORECASE).group(0),
                    reason=reason,
                ))

    return violations


MIN_CITATIONS = 3  # Letter must contain at least this many doc citations


def check_citation_count(db_conn) -> list[GateViolation]:
    """Verify the letter contains real documentation citations."""
    body = _get_letter_body(db_conn)
    if not body:
        return []

    # Match markdown links pointing to URLs: [text](http...)
    citations = re.findall(r'\[([^\]]+)\]\(https?://[^)]+\)', body)
    if len(citations) < MIN_CITATIONS:
        return [GateViolation(
            file="application-letter",
            line=0,
            phrase=f"found {len(citations)} citation(s), need {MIN_CITATIONS}+",
            reason=f"Letter must contain at least {MIN_CITATIONS} documentation citations",
        )]
    return []


def run_publish_gate(site_dir: str, db_conn, config) -> GateResult:
    """Run publish gate checks on the application letter."""
    violations = check_banned_phrases(db_conn)
    violations.extend(check_citation_count(db_conn))

    passed = len(violations) == 0

    parts = []
    if violations:
        parts.append(f"{len(violations)} violation(s) found in letter")
    if not parts:
        parts.append("all checks passed")

    return GateResult(
        passed=passed,
        violations=violations,
        chain_valid=True,
        summary="; ".join(parts),
    )


def export_claim_manifest(site_dir: str, db_conn, config, output_path: str) -> str:
    """Export a claim-evidence manifest as JSON."""
    import json
    from datetime import datetime, timezone

    gate = run_publish_gate(site_dir, db_conn, config)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate_passed": gate.passed,
        "summary": gate.summary,
        "violations": [
            {"file": v.file, "line": v.line, "phrase": v.phrase, "reason": v.reason}
            for v in gate.violations
        ],
        "db_metrics": {
            "doc_snapshots": count_rows(db_conn, "doc_snapshots"),
            "content_pieces": count_rows(db_conn, "content_pieces"),
            "growth_experiments": count_rows(db_conn, "growth_experiments"),
            "product_feedback": count_rows(db_conn, "product_feedback"),
            "seo_pages": count_rows(db_conn, "seo_pages"),
            "run_log": count_rows(db_conn, "run_log"),
            "community_interactions": count_rows(db_conn, "community_interactions"),
        },
    }

    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)

    return output_path
