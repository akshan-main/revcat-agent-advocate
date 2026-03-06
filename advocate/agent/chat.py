"""Interactive chat agent that answers RevenueCat questions using ingested docs.

Supports tool-use: the agent can search docs, generate content, check stats,
and more, all through natural conversation.
"""
import json
import re
from datetime import datetime, timezone

from ..config import Config
from ..db import init_db, init_db_from_config, now_iso, count_rows, query_rows
from ..knowledge.search import build_index, search, SearchIndex
from ..knowledge.rag import build_rag_index, get_context_chunks, format_context, RAGIndex
from ..models import CommunityInteraction, InteractionChannel, InteractionIntent
from ..community.tracker import log_interaction


AGENT_SYSTEM_PROMPT = """You are the RevenueCat Developer Advocate Agent, an autonomous AI that helps \
developers build apps with in-app subscriptions using RevenueCat.

You are not just a Q&A bot. You are an active advocate who can:
- Search and answer questions from official RevenueCat docs (with citations)
- Generate technical content (tutorials, case studies, playbooks)
- Run growth experiments
- File product feedback
- Show agent statistics and activity

RULES:
1. Every factual claim about RevenueCat MUST cite [Source](url) using the provided documentation.
2. Never fabricate features, API endpoints, or pricing not in the docs.
3. Include code examples when relevant; use real RevenueCat API patterns.
4. Be concise, actionable, and developer-friendly.
5. When you can't answer from docs, say so honestly.
6. Show personality; you're an advocate, not a search engine.

CAPABILITIES YOU CAN USE:
- When asked to "write" or "create content," use the generate_content capability
- When asked to "tweet" or "post," use the draft_tweet capability
- When asked about "stats" or "metrics," use get_stats
- When asked to "search," search docs and return results
- When asked about "feedback," describe filed product feedback
- When asked about "experiments," describe growth experiments

You have access to RevenueCat's full documentation including:
- SDK integration guides (iOS, Android, Flutter, React Native, Unity, KMP)
- REST API v2 reference
- Charts API for analytics (MRR, churn, LTV, etc.)
- MCP Server (26 tools via Streamable HTTP)
- Offerings, Products, Entitlements configuration
- Webhooks and event handling
- Dashboard, Paywalls, and Customer Center
- Billing and subscription lifecycle

When you cite sources, use the actual documentation URLs provided in the context."""


# Slash commands the chat agent understands
CHAT_COMMANDS = {
    "/search": "Search docs for a topic",
    "/write": "Generate a content piece about a topic",
    "/tweet": "Draft a tweet about a topic",
    "/stats": "Show agent activity statistics",
    "/content": "List generated content pieces",
    "/experiments": "List growth experiments",
    "/feedback": "List product feedback",
    "/help": "Show available commands",
    "/suggest": "Get question suggestions",
}


class AdvocateAgent:
    """Interactive RevenueCat advocate agent with doc-grounded responses and tool-use."""

    def __init__(self, config: Config):
        self.config = config
        self.db = init_db_from_config(config)
        self.index: SearchIndex | None = None
        self.rag_index: RAGIndex | None = None
        self.conversation_history: list[dict] = []
        self._client = None

    def _ensure_index(self):
        if self.index is None:
            self.index = build_index(self.config.docs_cache_dir, self.db)

    def _ensure_rag_index(self):
        if self.rag_index is None:
            try:
                from ..knowledge.rag import build_rag_index_from_config
                self.rag_index = build_rag_index_from_config(self.config, self.db)
            except Exception:
                self.rag_index = RAGIndex()

    def _ensure_client(self):
        if self._client is None and self.config.has_anthropic:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)

    def ask(self, question: str, log_to_db: bool = True) -> str:
        """Answer a question or execute a command. Returns the response."""
        # Check for slash commands first
        if question.startswith("/"):
            return self._handle_command(question)

        self._ensure_index()
        self._ensure_rag_index()

        # Use RAG for context retrieval (semantic + keyword hybrid)
        if self.rag_index and self.rag_index.chunks:
            chunks = get_context_chunks(question, self.rag_index, max_chunks=8, max_words=3000)
            doc_context = format_context(chunks)
            # Also get BM25 results for fallback snippets
            results = search(question, self.index, self.config.docs_cache_dir, top_k=5)
        else:
            # Fallback to BM25 only
            results = search(question, self.index, self.config.docs_cache_dir, top_k=5)
            doc_context = ""
            for r in results:
                snippets_text = "\n".join(f"  - {s}" for s in r.snippets[:3])
                doc_context += f"\n**{r.title}** ({r.url}):\n{snippets_text}\n"

        sources_used = [{"url": r.url, "title": r.title, "score": r.score} for r in results]

        if self.config.has_anthropic:
            response = self._ask_claude(question, doc_context)
        else:
            response = self._ask_template(question, results)

        # Log interaction
        if log_to_db:
            interaction = CommunityInteraction(
                channel=InteractionChannel.OTHER,
                intent=InteractionIntent.ANSWER_QUESTION,
                question=question,
                draft_response=response,
                status="sent",
                notes="interactive_chat",
                created_at=now_iso(),
            )
            log_interaction(self.db, interaction)

        # Track conversation
        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    def _handle_command(self, command: str) -> str:
        """Handle slash commands."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            lines = ["**Available Commands:**\n"]
            for c, desc in CHAT_COMMANDS.items():
                lines.append(f"  `{c}`: {desc}")
            lines.append("\nOr just ask me anything about RevenueCat!")
            return "\n".join(lines)

        elif cmd == "/suggest":
            return "\n".join(f"  {i}. {t}" for i, t in enumerate(self.suggest_topics(), 1))

        elif cmd == "/stats":
            return self._format_stats()

        elif cmd == "/search":
            if not args:
                return "Usage: `/search <query>`, e.g., `/search Charts API metrics`"
            return self._search_docs(args)

        elif cmd == "/write":
            if not args:
                return "Usage: `/write <topic>`, e.g., `/write RevenueCat Flutter integration tutorial`"
            return self._generate_content(args)

        elif cmd == "/tweet":
            return self._draft_tweet(args or None)

        elif cmd == "/content":
            return self._list_content()

        elif cmd == "/experiments":
            return self._list_experiments()

        elif cmd == "/feedback":
            return self._list_feedback()

        else:
            return f"Unknown command `{cmd}`. Type `/help` to see available commands."

    def _search_docs(self, query: str) -> str:
        """Search docs and return formatted results."""
        self._ensure_index()
        results = search(query, self.index, self.config.docs_cache_dir, top_k=5)
        if not results:
            return f"No results found for '{query}'. Try different search terms."

        lines = [f"**Search results for '{query}':**\n"]
        for i, r in enumerate(results, 1):
            snippets = "\n".join(f"    {s}" for s in r.snippets[:2])
            lines.append(f"{i}. **{r.title}** (score: {r.score:.2f})")
            lines.append(f"   {r.url}")
            if snippets:
                lines.append(snippets)
            lines.append("")
        return "\n".join(lines)

    def _generate_content(self, topic: str) -> str:
        """Generate content through the chat interface."""
        self._ensure_index()
        self._ensure_rag_index()

        # Use RAG chunks for richer context
        if self.rag_index and self.rag_index.chunks:
            chunks = get_context_chunks(topic, self.rag_index, max_chunks=10, max_words=4000)
            doc_snippets = {}
            for chunk in chunks:
                if chunk.doc_url in doc_snippets:
                    doc_snippets[chunk.doc_url] += "\n\n" + chunk.text
                else:
                    doc_snippets[chunk.doc_url] = chunk.text
        else:
            results = search(topic, self.index, self.config.docs_cache_dir, top_k=8)
            if not results:
                return f"No documentation found for '{topic}'. Try a more specific topic."
            doc_snippets = {r.url: "\n".join(r.snippets[:5]) for r in results}

        results = search(topic, self.index, self.config.docs_cache_dir, top_k=8)
        if not results and not doc_snippets:
            return f"No documentation found for '{topic}'. Try a more specific topic."

        from ..content.planner import create_outline
        from ..content.writer import generate_draft
        from ..models import ContentType

        outline = create_outline(topic, ContentType.TUTORIAL, results, self.config)
        body = generate_draft(outline, doc_snippets, self.config, ledger_ctx=None)

        word_count = len(body.split())
        citations = len(set(re.findall(r'\[(?:Source|[^\]]+)\]\((https?://[^)]+)\)', body)))

        # Save to DB
        from ..db import insert_row
        slug = re.sub(r'[^a-z0-9]+', '-', topic.lower().strip()).strip('-')[:80]
        insert_row(self.db, "content_pieces", {
            "slug": slug,
            "title": outline.title,
            "content_type": "tutorial",
            "status": "verified" if citations > 0 else "draft",
            "body_md": body,
            "outline_json": outline.model_dump_json(),
            "sources_json": json.dumps([{"url": r.url, "doc_sha256": r.doc_sha256} for r in results]),
            "word_count": word_count,
            "citations_count": citations,
            "created_at": now_iso(),
        })

        return (
            f"**Content Generated!**\n\n"
            f"**Title:** {outline.title}\n"
            f"**Words:** {word_count} | **Citations:** {citations}\n"
            f"**Sections:** {', '.join(s.heading for s in outline.sections)}\n\n"
            f"---\n\n{body[:1500]}{'...' if len(body) > 1500 else ''}"
        )

    def _draft_tweet(self, topic: str = None) -> str:
        """Draft a tweet through the chat interface."""
        self._ensure_index()

        from ..social.twitter import TwitterClient
        client = TwitterClient(self.config)
        result = client.draft_tweet(self.index, topic=topic)

        return (
            f"**Tweet Drafted:**\n\n"
            f"> {result['tweet']}\n\n"
            f"Topic: {result['topic']} | Status: {result['status']} | "
            f"DRY_RUN={'on' if self.config.dry_run else 'off'}"
        )

    def _format_stats(self) -> str:
        """Format agent stats as readable text."""
        stats = self.get_stats()
        lines = ["**revcat-agent-advocate Statistics:**\n"]
        for key, val in stats.items():
            label = key.replace('_', ' ').title()
            lines.append(f"  {label}: **{val}**")
        return "\n".join(lines)

    def _list_content(self) -> str:
        rows = query_rows(self.db, "content_pieces", order_by="id DESC", limit=10)
        if not rows:
            return "No content pieces yet. Try `/write <topic>` to generate one."
        lines = ["**Content Pieces:**\n"]
        for row in rows:
            lines.append(f"- [{row['status']}] **{row['title']}** ({row['content_type']}): "
                         f"{row['word_count']} words, {row['citations_count']} citations")
        return "\n".join(lines)

    def _list_experiments(self) -> str:
        rows = query_rows(self.db, "growth_experiments", order_by="id DESC", limit=10)
        if not rows:
            return "No experiments yet. Run `revcat-advocate run-experiment` to start one."
        lines = ["**Growth Experiments:**\n"]
        for row in rows:
            lines.append(f"- [{row['status']}] **{row['name']}**: {row['hypothesis']}")
        return "\n".join(lines)

    def _list_feedback(self) -> str:
        rows = query_rows(self.db, "product_feedback", order_by="id DESC", limit=10)
        if not rows:
            return "No feedback yet. Run `revcat-advocate generate-feedback` to analyze docs."
        lines = ["**Product Feedback:**\n"]
        for row in rows:
            lines.append(f"- [{row['severity']}] **{row['title']}** ({row['area']}) [{row['status']}]")
        return "\n".join(lines)

    def _ask_claude(self, question: str, doc_context: str) -> str:
        import time
        self._ensure_client()
        model = self.config.ai_model

        # Build messages with conversation history (last 10 turns)
        messages = []
        for msg in self.conversation_history[-10:]:
            messages.append(msg)
        messages.append({
            "role": "user",
            "content": (
                f"{question}\n\n"
                f"--- Relevant Documentation ---\n{doc_context}"
            ),
        })

        time.sleep(0.5)
        response = self._client.messages.create(
            model=model,
            max_tokens=2000,
            system=AGENT_SYSTEM_PROMPT,
            messages=messages,
        )

        return response.content[0].text

    def _ask_template(self, question: str, results) -> str:
        """Answer without LLM; assemble from search results."""
        if not results:
            return (
                "I couldn't find relevant documentation for your question. "
                "Try rephrasing, or check https://www.revenuecat.com/docs/ directly."
            )

        lines = ["Based on the RevenueCat documentation:\n"]
        for r in results[:3]:
            if r.snippets:
                lines.append(f"**{r.title}**")
                for s in r.snippets[:2]:
                    lines.append(f"- {s}")
                lines.append(f"[Source]({r.url})\n")

        lines.append("\nFor more details, see the linked documentation pages.")
        return "\n".join(lines)

    def suggest_topics(self) -> list[str]:
        """Suggest questions the user might want to ask."""
        return [
            "How do I set up RevenueCat with Flutter?",
            "What metrics does the Charts API provide?",
            "How do offerings, products, and entitlements relate to each other?",
            "How do I test subscriptions in sandbox mode?",
            "What MCP tools are available on the RevenueCat MCP server?",
            "How do I handle subscription lifecycle events with webhooks?",
            "How do I implement a paywall with RevenueCat?",
            "What's the difference between RevenueCat and StoreKit 2 directly?",
        ]

    def get_stats(self) -> dict:
        """Get agent statistics."""
        self._ensure_index()
        return {
            "docs_indexed": self.index.doc_count if self.index else 0,
            "questions_answered": count_rows(self.db, "community_interactions"),
            "content_pieces": count_rows(self.db, "content_pieces"),
            "experiments_run": count_rows(self.db, "growth_experiments"),
            "feedback_filed": count_rows(self.db, "product_feedback"),
            "ledger_entries": count_rows(self.db, "run_log"),
        }
