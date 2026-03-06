from ..models import ProductFeedback, Severity, FeedbackArea
from ..db import insert_row, query_rows, now_iso


def create_feedback(
    title: str,
    severity: Severity,
    area: FeedbackArea,
    repro_steps: str = "",
    expected: str = "",
    actual: str = "",
    evidence_links: list[str] | None = None,
    proposed_fix: str = "",
) -> ProductFeedback:
    """Create a validated ProductFeedback object."""
    return ProductFeedback(
        title=title,
        severity=severity,
        area=area,
        repro_steps=repro_steps,
        expected=expected,
        actual=actual,
        evidence_links=evidence_links or [],
        proposed_fix=proposed_fix,
        created_at=now_iso(),
    )


def save_feedback(db_conn, feedback: ProductFeedback) -> int:
    """Insert feedback into the database. Returns row id."""
    return insert_row(db_conn, "product_feedback", {
        "title": feedback.title,
        "severity": feedback.severity.value,
        "area": feedback.area.value,
        "repro_steps": feedback.repro_steps,
        "expected": feedback.expected,
        "actual": feedback.actual,
        "evidence_links_json": feedback.evidence_links,
        "proposed_fix": feedback.proposed_fix,
        "status": feedback.status,
        "created_at": feedback.created_at or now_iso(),
    })


def list_feedback(
    db_conn,
    status: str | None = None,
    area: str | None = None,
) -> list[dict]:
    where = {}
    if status:
        where["status"] = status
    if area:
        where["area"] = area
    return query_rows(db_conn, "product_feedback", where=where or None)


def generate_feedback_from_docs(
    search_index,
    config,
    db_conn,
    ledger_ctx=None,
    count: int = 3,
) -> list[ProductFeedback]:
    """Use Claude API to analyze docs and generate structured feedback."""
    if config and config.has_anthropic:
        return _generate_with_claude(search_index, config, db_conn, ledger_ctx, count)
    return _generate_placeholder_feedback(count)


def _generate_with_claude(search_index, config, db_conn, ledger_ctx, count):
    import json
    import anthropic
    from ..knowledge.search import search as search_docs

    import time

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = config.ai_model

    # Search a variety of doc areas for analysis
    areas = ["charts API", "MCP server", "offerings paywalls", "SDK installation", "webhooks"]
    doc_context = []
    for area in areas:
        results = search_docs(area, search_index, config.docs_cache_dir, top_k=2)
        for r in results:
            doc_context.append(f"**{r.title}** ({r.url}):\n" + "\n".join(f"  - {s}" for s in r.snippets[:2]))

    system = (
        "You are a QA engineer reviewing RevenueCat documentation. "
        "Analyze the provided documentation snippets and identify issues:\n"
        "1. Inconsistencies between docs pages\n"
        "2. Missing information that developers would need\n"
        "3. Unclear or confusing explanations\n"
        "4. API endpoints mentioned without examples\n\n"
        f"Generate exactly {count} feedback items as a JSON array:\n"
        '[{"title": "...", "severity": "minor|major|suggestion", '
        '"area": "docs|api|charts|sdk|mcp|offerings|dashboard|paywalls|other", '
        '"repro_steps": "...", "expected": "...", "actual": "...", '
        '"evidence_links": ["url1"], "proposed_fix": "..."}]'
    )

    time.sleep(0.5)  # Rate limit between API calls
    message = client.messages.create(
        model=model,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": "\n\n".join(doc_context[:10])}],
    )

    if ledger_ctx:
        from ..ledger import log_tool_call
        log_tool_call(ledger_ctx, "anthropic.messages.create", "generate_feedback", f"tokens={message.usage.output_tokens}")

    # Parse response
    text = message.content[0].text
    try:
        start = text.index("[")
        end = text.rindex("]") + 1
        items = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return _generate_placeholder_feedback(count)

    feedbacks = []
    for item in items[:count]:
        try:
            fb = create_feedback(
                title=item.get("title", "Documentation issue"),
                severity=Severity(item.get("severity", "suggestion")),
                area=FeedbackArea(item.get("area", "docs")),
                repro_steps=item.get("repro_steps", ""),
                expected=item.get("expected", ""),
                actual=item.get("actual", ""),
                evidence_links=item.get("evidence_links", []),
                proposed_fix=item.get("proposed_fix", ""),
            )
            save_feedback(db_conn, fb)
            feedbacks.append(fb)
        except (ValueError, KeyError):
            continue

    return feedbacks


def _generate_placeholder_feedback(count: int) -> list[ProductFeedback]:
    """Generate basic placeholder feedback (no LLM)."""
    templates = [
        ("Charts API documentation lacks code examples", Severity.MINOR, FeedbackArea.DOCS),
        ("MCP server tool descriptions could be more detailed", Severity.SUGGESTION, FeedbackArea.MCP),
        ("SDK installation guide missing troubleshooting section", Severity.MINOR, FeedbackArea.DOCS),
        ("API v2 error responses not documented for all endpoints", Severity.MAJOR, FeedbackArea.API),
        ("Offerings configuration guide needs agent-specific examples", Severity.SUGGESTION, FeedbackArea.OFFERINGS),
    ]

    feedbacks = []
    for i in range(min(count, len(templates))):
        title, severity, area = templates[i]
        feedbacks.append(create_feedback(
            title=title,
            severity=severity,
            area=area,
            repro_steps=f"Navigate to the {area.value} documentation section",
            expected="Clear, complete documentation with examples",
            actual="Documentation is missing key details",
            proposed_fix=f"Add detailed examples and edge cases to {area.value} docs",
        ))

    return feedbacks
