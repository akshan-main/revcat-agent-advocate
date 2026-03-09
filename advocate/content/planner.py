from ..models import ContentOutline, ContentType, Section, SearchResult

SUGGESTED_TOPICS = [
    "Getting Started with RevenueCat Charts API for Agent Dashboards",
    "Building Agent-Native Monetization with RevenueCat MCP Server",
    "RevenueCat Offerings and Paywalls: A Technical Deep Dive for Agents",
    "Implementing Subscription Analytics with the RevenueCat REST API v2",
    "How Agentic AI Apps Should Handle In-App Purchase Lifecycle Events",
    "RevenueCat Entitlements: Managing Access Control Programmatically",
    "Migrating to RevenueCat: A Step-by-Step Guide for Existing Apps",
    "Testing In-App Purchases with RevenueCat Sandbox Mode",
    "RevenueCat Webhooks: Real-Time Subscription Event Processing",
    "Cross-Platform Subscription Management with RevenueCat SDKs",
]


def suggest_topics(search_index=None, count: int = 5) -> list[str]:
    """Suggest content topics, optionally enhanced by doc coverage analysis."""
    topics = list(SUGGESTED_TOPICS)

    if search_index and search_index.doc_count > 0:
        # Find categories with fewer indexed docs (potential content gaps)
        category_counts: dict[str, int] = {}
        for title in search_index.doc_titles.values():
            words = title.lower().split()
            for word in ["charts", "mcp", "offerings", "paywalls", "webhooks", "sdk", "api"]:
                if word in " ".join(words):
                    category_counts[word] = category_counts.get(word, 0) + 1

    return topics[:count]


def create_outline(
    topic: str,
    content_type: ContentType,
    search_results: list[SearchResult],
    config=None,
) -> ContentOutline:
    """Create a content outline using Claude API."""
    if not config or not config.has_anthropic:
        raise RuntimeError("Anthropic API key required for content outline generation. Set ANTHROPIC_API_KEY.")
    return _create_outline_with_claude(topic, content_type, search_results, config)


def _create_outline_with_claude(
    topic: str,
    content_type: ContentType,
    search_results: list[SearchResult],
    config,
) -> ContentOutline:
    """Use Claude API to generate a structured outline."""
    import anthropic

    import time

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = config.ai_model

    # Build context from search results
    doc_context = []
    for r in search_results[:5]:
        snippets_text = "\n".join(f"  - {s}" for s in r.snippets[:3])
        doc_context.append(f"**{r.title}** ({r.url}):\n{snippets_text}")

    context_str = "\n\n".join(doc_context)

    system_prompt = (
        f"You are a technical content planner for RevenueCat developer documentation. "
        f"Create a structured outline for a {content_type.value} about '{topic}'. "
        f"Use ONLY information from the provided documentation snippets. "
        f"Each section must reference specific documentation sources.\n\n"
        f"Respond in this exact JSON format:\n"
        f'{{"title": "...", "sections": [{{"heading": "...", "key_points": ["..."], '
        f'"source_refs": ["url1"], "has_code_snippet": true/false}}], '
        f'"estimated_word_count": 1500}}'
    )

    time.sleep(0.5)  # Rate limit between API calls
    message = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Documentation context:\n\n{context_str}"}],
    )

    # Parse response
    import json
    text = message.content[0].text
    # Try to extract JSON from the response
    try:
        # Find JSON in response
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        raise RuntimeError(f"Failed to parse Claude outline response as JSON: {text[:200]}")

    sections = []
    for s in data.get("sections", []):
        sections.append(Section(
            heading=s.get("heading", ""),
            key_points=s.get("key_points", []),
            source_refs=s.get("source_refs", []),
            has_code_snippet=s.get("has_code_snippet", False),
        ))

    return ContentOutline(
        title=data.get("title", topic),
        content_type=content_type,
        sections=sections,
        sources=[r.url for r in search_results[:5]],
        estimated_word_count=data.get("estimated_word_count", 1500),
    )


