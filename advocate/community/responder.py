from ..models import CommunityInteraction, InteractionChannel, InteractionIntent, SearchResult
from ..db import now_iso
from .tracker import log_interaction


def draft_response(
    question: str,
    search_results: list[SearchResult],
    config=None,
    ledger_ctx=None,
) -> str:
    """Draft a response to a community question using doc context."""
    if config and config.has_anthropic:
        return _draft_with_claude(question, search_results, config, ledger_ctx)
    return _draft_from_results(question, search_results)


def _draft_with_claude(question, search_results, config, ledger_ctx):
    import time
    import anthropic

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = config.ai_model

    # Try RAG for richer context
    doc_context = ""
    try:
        from ..knowledge.rag import build_rag_index_from_config, get_context_chunks, format_context
        from ..db import init_db_from_config
        db = init_db_from_config(config)
        rag_index = build_rag_index_from_config(config, db)
        if rag_index.chunks:
            chunks = get_context_chunks(question, rag_index, max_chunks=6, max_words=2000)
            doc_context = format_context(chunks)
    except Exception:
        pass

    # Fall back to search result snippets if RAG didn't produce context
    if not doc_context:
        doc_context = "\n\n".join(
            f"**{r.title}** ({r.url}):\n" + "\n".join(f"- {s}" for s in r.snippets[:2])
            for r in search_results[:5]
        )

    system = (
        "You are a helpful RevenueCat developer advocate. "
        "Answer the question using ONLY the provided documentation. "
        "Include [Source](url) citations for every factual claim. "
        "Be concise and actionable. Keep response under 300 words."
    )

    time.sleep(0.5)  # Rate limit between API calls
    message = client.messages.create(
        model=model,
        max_tokens=1000,
        system=system,
        messages=[{
            "role": "user",
            "content": f"Question: {question}\n\nDocumentation:\n{doc_context}",
        }],
    )

    if ledger_ctx:
        from ..ledger import log_tool_call
        log_tool_call(ledger_ctx, "anthropic.messages.create", "community_response", f"tokens={message.usage.output_tokens}")

    return message.content[0].text


def _draft_from_results(question, search_results):
    lines = [f"Regarding your question about: {question}\n"]

    for r in search_results[:3]:
        if r.snippets:
            lines.append(f"From the docs: {r.snippets[0]}")
            lines.append(f"[Source]({r.url})\n")

    lines.append("For more details, check the RevenueCat documentation.")
    return "\n".join(lines)


def queue_responses(
    db_conn,
    questions: list[dict],
    search_index,
    config=None,
    ledger_ctx=None,
) -> list[int]:
    """Draft and queue responses for a batch of questions. NEVER auto-posts."""
    from ..knowledge.search import search as search_docs

    ids = []
    for q in questions:
        question_text = q.get("question", q.get("text", ""))
        channel = q.get("channel", "github")
        counterpart = q.get("counterpart", q.get("user", ""))
        thread_url = q.get("thread_url", q.get("url", ""))

        # Search docs
        results = search_docs(question_text, search_index, config.docs_cache_dir if config else "./.docs_cache", top_k=5)

        # Draft response
        response = draft_response(question_text, results, config, ledger_ctx)

        # Log as draft; NEVER auto-post
        interaction = CommunityInteraction(
            channel=InteractionChannel(channel),
            thread_url=thread_url,
            counterpart=counterpart,
            intent=InteractionIntent.ANSWER_QUESTION,
            question=question_text,
            draft_response=response,
            status="draft",
            created_at=now_iso(),
        )

        row_id = log_interaction(db_conn, interaction)
        ids.append(row_id)

    return ids
