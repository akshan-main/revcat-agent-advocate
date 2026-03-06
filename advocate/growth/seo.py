import re
from ..models import SearchResult
from ..db import insert_row, now_iso

DEFAULT_SEO_KEYWORDS = [
    "RevenueCat vs Adapty",
    "RevenueCat vs Qonversion",
    "RevenueCat vs Glassfy",
    "How to implement subscriptions with RevenueCat",
    "How to add paywalls with RevenueCat",
    "How to track MRR with RevenueCat Charts",
    "What is RevenueCat MCP server",
    "RevenueCat API v2 getting started",
    "RevenueCat subscription analytics for agents",
    "In-app purchase monetization for AI-built apps",
]


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')


def determine_template_type(keyword: str) -> str:
    kw = keyword.lower()
    if " vs " in kw:
        return "comparison"
    if kw.startswith("how to"):
        return "how_to"
    return "glossary"


def generate_seo_page(
    keyword: str,
    search_results: list[SearchResult],
    config=None,
    ledger_ctx=None,
) -> tuple[str, str]:
    """Generate a single SEO page. Returns (body_md, slug)."""
    template_type = determine_template_type(keyword)
    slug = _slugify(keyword)

    # Build doc context
    sources_md = "\n".join(f"- [{r.title}]({r.url})" for r in search_results[:5])
    snippets = []
    for r in search_results[:3]:
        for s in r.snippets[:2]:
            snippets.append(s)

    if config and config.has_anthropic:
        body_md = _generate_seo_with_claude(keyword, template_type, search_results, sources_md, config, ledger_ctx)
    else:
        body_md = _generate_seo_from_template(keyword, template_type, snippets, sources_md)

    return body_md, slug


def _generate_seo_with_claude(keyword, template_type, search_results, sources_md, config, ledger_ctx):
    import time
    import anthropic

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = config.ai_model

    doc_context = "\n\n".join(
        f"**{r.title}** ({r.url}):\n" + "\n".join(f"- {s}" for s in r.snippets[:2])
        for r in search_results[:5]
    )

    system = (
        f"Write a concise, SEO-optimized article about '{keyword}'. "
        f"Type: {template_type}. "
        f"Every factual claim must cite [Source](url) from the provided docs. "
        f"Include a ## Sources section at the end. "
        f"Use markdown. Keep it under 800 words."
    )

    time.sleep(0.5)  # Rate limit between API calls
    message = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": f"Documentation:\n\n{doc_context}"}],
    )

    if ledger_ctx:
        from ..ledger import log_tool_call
        log_tool_call(ledger_ctx, "anthropic.messages.create", "seo_page", f"tokens={message.usage.output_tokens}")

    return message.content[0].text


def _generate_seo_from_template(keyword, template_type, snippets, sources_md):
    body = f"# {keyword}\n\n"

    if template_type == "comparison":
        body += "## Overview\n\n"
        body += f"This article compares {keyword} to help developers choose the right subscription platform.\n\n"
        body += "## Feature Comparison\n\n"
        for s in snippets[:3]:
            body += f"- {s}\n"
        body += "\n## Why RevenueCat\n\n"
        body += "RevenueCat provides a unified API for managing in-app subscriptions across platforms.\n\n"
    elif template_type == "how_to":
        body += "## What You'll Learn\n\n"
        body += f"A step-by-step guide on {keyword.lower()}.\n\n"
        body += "## Steps\n\n"
        for i, s in enumerate(snippets[:5], 1):
            body += f"{i}. {s}\n\n"
    else:  # glossary
        body += "## Definition\n\n"
        body += f"{keyword} is a concept in subscription monetization.\n\n"
        body += "## How It Works in RevenueCat\n\n"
        for s in snippets[:3]:
            body += f"- {s}\n"
        body += "\n"

    body += f"## Sources\n\n{sources_md}\n"
    return body


def bulk_generate(
    db_conn,
    config,
    search_index,
    keywords: list[str] | None,
    experiment_id: int,
    ledger_ctx=None,
    output_dir: str = "./site_output",
) -> list[str]:
    """Generate multiple SEO pages. Returns list of slugs."""
    import os
    from ..knowledge.search import search as search_docs

    if keywords is None:
        keywords = DEFAULT_SEO_KEYWORDS

    slugs = []
    for keyword in keywords:
        # Search docs for keyword
        results = search_docs(keyword, search_index, config.docs_cache_dir, top_k=5)

        if not results:
            if ledger_ctx:
                from ..ledger import log_tool_call
                log_tool_call(ledger_ctx, "seo.skip", keyword, "No source docs found, skipping")
            continue

        body_md, slug = generate_seo_page(keyword, results, config, ledger_ctx)

        # Save
        post_dir = os.path.join(output_dir, "content", slug)
        os.makedirs(post_dir, exist_ok=True)
        with open(os.path.join(post_dir, "index.md"), "w") as f:
            f.write(body_md)

        # Insert into DB
        insert_row(db_conn, "seo_pages", {
            "keyword": keyword,
            "template_type": determine_template_type(keyword),
            "slug": slug,
            "title": keyword,
            "body_md": body_md,
            "sources_json": [r.url for r in results[:5]],
            "experiment_id": experiment_id,
            "created_at": now_iso(),
        })

        slugs.append(slug)

    return slugs
