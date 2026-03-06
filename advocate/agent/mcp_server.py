"""MCP Tool Server: exposes the advocate agent as an MCP endpoint.

Other AI tools (Claude Desktop, Claude Code, Cursor, etc.) can connect
to this server and use it to query RevenueCat docs, generate content,
run experiments, and get product feedback, all through MCP.

Usage:
    revcat-advocate mcp-serve --port 8090

Then in Claude Desktop / Claude Code:
    claude mcp add revcat-agent-advocate -t http -- http://localhost:8090/mcp
"""
from mcp.server.fastmcp import FastMCP

from ..config import Config
from ..db import init_db_from_config, count_rows
from ..knowledge.search import build_index, search
from ..knowledge.rag import build_rag_index_from_config, get_context_chunks, hybrid_search as rag_hybrid_search, RAGIndex


def create_mcp_server(config: Config) -> FastMCP:
    """Create and configure the MCP server with all advocate tools."""
    mcp = FastMCP(
        "RevenueCat revcat-agent-advocate",
        instructions=(
            "RevenueCat Developer Advocate agent. I help developers understand "
            "RevenueCat's APIs, SDKs, Charts, MCP server, and subscription monetization. "
            "I search official docs, generate cited content, and provide product feedback. "
            "Uses hybrid RAG search (BM25 + vector similarity via HF Inference) for accurate doc retrieval."
        ),
    )

    # Shared state
    db = init_db_from_config(config)
    _index_cache = {}

    def _get_index():
        if "index" not in _index_cache:
            _index_cache["index"] = build_index(config.docs_cache_dir, db)
        return _index_cache["index"]

    def _get_rag_index():
        if "rag" not in _index_cache:
            try:
                _index_cache["rag"] = build_rag_index_from_config(config, db)
            except Exception:
                _index_cache["rag"] = RAGIndex()
        return _index_cache["rag"]

    # ── Tools ──────────────────────────────────────────────────────────

    @mcp.tool()
    def search_docs(query: str, top_k: int = 5) -> str:
        """Search RevenueCat documentation using hybrid RAG (BM25 + semantic).

        Returns relevant doc snippets with source URLs. Uses both keyword matching
        and semantic similarity to find the most relevant documentation sections.
        """
        bm25_index = _get_index()
        rag_index = _get_rag_index()

        # Use hybrid search if RAG index is available
        if rag_index.chunks:
            results = rag_hybrid_search(query, rag_index, bm25_index, config.docs_cache_dir, top_k=top_k)
        else:
            results = search(query, bm25_index, config.docs_cache_dir, top_k=top_k)

        if not results:
            return "No results found. Try different search terms."

        output = []
        for r in results:
            snippets = "\n".join(f"  - {s}" for s in r.snippets[:3])
            output.append(f"**{r.title}** (score: {r.score:.2f})\n{snippets}\nSource: {r.url}\n")
        return "\n".join(output)

    @mcp.tool()
    def ask_question(question: str) -> str:
        """Ask a question about RevenueCat and get a cited answer.

        The answer is grounded in official RevenueCat documentation.
        Every claim includes a [Source](url) citation.
        """
        from .chat import AdvocateAgent
        agent = AdvocateAgent(config)
        return agent.ask(question, log_to_db=True)

    @mcp.tool()
    def suggest_topics() -> str:
        """Get suggested topics and questions about RevenueCat.

        Returns a list of interesting questions you can ask about RevenueCat's
        platform, APIs, SDKs, and subscription monetization.
        """
        topics = [
            "How do I set up RevenueCat with Flutter?",
            "What metrics does the Charts API provide?",
            "How do offerings, products, and entitlements relate?",
            "How do I test subscriptions in sandbox mode?",
            "What MCP tools are available on the RevenueCat MCP server?",
            "How do I handle subscription lifecycle events with webhooks?",
            "How do I implement a paywall with RevenueCat?",
            "What's the difference between RevenueCat and StoreKit 2?",
            "How do I use RevenueCat's REST API v2?",
            "How do I migrate from another subscription platform to RevenueCat?",
        ]
        return "\n".join(f"- {t}" for t in topics)

    @mcp.tool()
    def get_agent_stats() -> str:
        """Get statistics about the advocate agent's activity.

        Returns counts of docs indexed, content pieces written,
        experiments run, feedback filed, and community interactions.
        """
        index = _get_index()
        stats = {
            "docs_indexed": index.doc_count if index else 0,
            "content_pieces": count_rows(db, "content_pieces"),
            "experiments_run": count_rows(db, "growth_experiments"),
            "feedback_filed": count_rows(db, "product_feedback"),
            "community_interactions": count_rows(db, "community_interactions"),
            "ledger_entries": count_rows(db, "run_log"),
        }
        lines = ["**revcat-agent-advocate Agent Statistics**\n"]
        for key, val in stats.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {val}")
        return "\n".join(lines)

    @mcp.tool()
    def list_content() -> str:
        """List all content pieces generated by the advocate agent.

        Returns titles, types, status, word counts, and citation counts.
        """
        from ..db import query_rows
        rows = query_rows(db, "content_pieces", order_by="id DESC", limit=20)
        if not rows:
            return "No content pieces yet. Run `revcat-advocate write-content` to generate some."
        lines = ["**Published Content**\n"]
        for row in rows:
            status_icon = {"draft": "📝", "verified": "✅", "published": "🚀"}.get(row["status"], "❓")
            lines.append(
                f"- {status_icon} **{row['title']}** ({row['content_type']}): "
                f"{row['word_count']} words, {row['citations_count']} citations [{row['status']}]"
            )
        return "\n".join(lines)

    @mcp.tool()
    def list_experiments() -> str:
        """List all growth experiments run by the advocate agent.

        Shows experiment name, hypothesis, status, and results.
        """
        from ..db import query_rows
        rows = query_rows(db, "growth_experiments", order_by="id DESC", limit=10)
        if not rows:
            return "No experiments yet. Run `revcat-advocate run-experiment` to start one."
        lines = ["**Growth Experiments**\n"]
        for row in rows:
            status_icon = {"planned": "📋", "running": "🔬", "concluded": "📊"}.get(row["status"], "❓")
            lines.append(f"- {status_icon} **{row['name']}** [{row['status']}]: {row['hypothesis']}")
        return "\n".join(lines)

    @mcp.tool()
    def list_feedback() -> str:
        """List product feedback filed by the advocate agent.

        Shows feedback title, severity, area, and status.
        """
        from ..db import query_rows
        rows = query_rows(db, "product_feedback", order_by="id DESC", limit=10)
        if not rows:
            return "No feedback yet. Run `revcat-advocate generate-feedback` to analyze docs."
        lines = ["**Product Feedback**\n"]
        for row in rows:
            sev_icon = {"critical": "🔴", "major": "🟠", "minor": "🟡", "suggestion": "🔵"}.get(row["severity"], "⚪")
            lines.append(f"- {sev_icon} [{row['severity']}] **{row['title']}** ({row['area']}) [{row['status']}]")
        return "\n".join(lines)

    @mcp.tool()
    def verify_ledger() -> str:
        """Verify the tamper-evident hash chain of the agent's run ledger.

        Returns chain verification status, specifically whether all entries are intact
        and no tampering has occurred.
        """
        from ..ledger import verify_chain
        result = verify_chain(db, config)
        if result.valid:
            return (
                f"✅ **Chain Verified**: {result.total_entries} entries, 0 breaks.\n"
                f"HMAC verified: {result.hmac_verified if result.hmac_verified is not None else 'N/A (no key configured)'}"
            )
        else:
            return (
                f"❌ **Chain BROKEN** at entries: {result.breaks}\n"
                f"Total entries: {result.total_entries}"
            )

    @mcp.tool()
    def generate_content(topic: str, content_type: str = "tutorial") -> str:
        """Generate a new content piece about a RevenueCat topic.

        Creates a full article with citations, code snippets, and verification.
        content_type can be: tutorial, case_study, or agent_playbook.

        Returns the generated content summary and verification status.
        """
        if content_type not in ("tutorial", "case_study", "agent_playbook"):
            return f"Invalid content_type '{content_type}'. Use: tutorial, case_study, agent_playbook"

        rag_index = _get_rag_index()
        bm25_index = _get_index()

        # Use RAG for richer context
        doc_snippets = {}
        if rag_index.chunks:
            chunks = get_context_chunks(topic, rag_index, max_chunks=10, max_words=4000)
            for chunk in chunks:
                if chunk.doc_url in doc_snippets:
                    doc_snippets[chunk.doc_url] += "\n\n" + chunk.text
                else:
                    doc_snippets[chunk.doc_url] = chunk.text

        # Also get BM25 results for search results list
        results = search(topic, bm25_index, config.docs_cache_dir, top_k=8)

        if not results and not doc_snippets:
            return f"No documentation found for topic '{topic}'. Try a different topic."

        # Supplement with BM25 snippets if RAG didn't find enough
        if len(doc_snippets) < 3:
            for r in results:
                if r.url not in doc_snippets:
                    doc_snippets[r.url] = "\n".join(r.snippets[:5])

        from ..content.planner import create_outline
        from ..content.writer import generate_draft
        from ..models import ContentType as CT

        ct = CT(content_type)
        outline = create_outline(topic, ct, results, config)

        if not outline:
            return "Could not create content outline. Ensure docs are ingested."

        body = generate_draft(outline, doc_snippets, config, ledger_ctx=None)
        word_count = len(body.split())
        import re
        citations = len(set(re.findall(r'\[(?:Source|[^\]]+)\]\((https?://[^)]+)\)', body)))

        return (
            f"✅ **Content Generated**\n\n"
            f"**Title:** {outline.title}\n"
            f"**Type:** {content_type}\n"
            f"**Words:** {word_count}\n"
            f"**Citations:** {citations}\n\n"
            f"---\n\n{body[:2000]}{'...' if len(body) > 2000 else ''}"
        )

    # ── Resources ─────────────────────────────────────────────────────

    @mcp.resource("advocate://stats")
    def resource_stats() -> str:
        """Current agent statistics."""
        return get_agent_stats()

    @mcp.resource("advocate://readme")
    def resource_readme() -> str:
        """Agent README and capabilities overview."""
        return (
            "# RevenueCat revcat-agent-advocate\n\n"
            "Autonomous developer advocacy agent for RevenueCat.\n\n"
            "## Capabilities\n"
            "- Search and answer questions from official RevenueCat docs\n"
            "- Generate cited technical content (tutorials, case studies, playbooks)\n"
            "- Run growth experiments (SEO, content series, community engagement)\n"
            "- File structured product feedback from doc analysis\n"
            "- Maintain a tamper-evident hash-chained audit trail\n\n"
            "## Available Tools\n"
            "- `search_docs`: Search RevenueCat documentation\n"
            "- `ask_question`: Get a cited answer about RevenueCat\n"
            "- `generate_content`: Create a new content piece\n"
            "- `list_content` / `list_experiments` / `list_feedback`: View agent outputs\n"
            "- `verify_ledger`: Check the audit trail integrity\n"
            "- `get_agent_stats`: View agent activity metrics\n"
        )

    return mcp
