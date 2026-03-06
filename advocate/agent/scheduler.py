"""Autonomous scheduler: runs the agent on a schedule without human intervention.

This is what makes the agent truly autonomous. It can:
- Generate content on a cadence
- Check for community questions and draft responses
- Run growth experiments
- Generate product feedback
- Build and publish the site

Usage:
    revcat-advocate auto --interval 6h
    revcat-advocate auto --once      # Run all tasks once and exit
"""
import json
import random
import time
import traceback
from datetime import datetime, timezone, timedelta

from ..config import Config
from ..db import init_db, init_db_from_config, count_rows, query_rows, now_iso


# Content topics the agent can write about autonomously
AUTONOMOUS_TOPICS = [
    "Getting Started with RevenueCat Charts API for Agent Dashboards",
    "Building Agent-Native Monetization with RevenueCat MCP Server",
    "RevenueCat Offerings and Paywalls: A Technical Deep Dive",
    "Implementing Subscription Analytics with the RevenueCat REST API v2",
    "How Agentic AI Apps Should Handle In-App Purchase Lifecycle Events",
    "RevenueCat vs StoreKit 2: When to Use Each for Subscription Management",
    "Building a Paywall with RevenueCat: Step-by-Step Tutorial",
    "Understanding RevenueCat Entitlements for Multi-Platform Apps",
    "Migrating from Adapty to RevenueCat: A Complete Guide",
    "RevenueCat Webhooks: Real-Time Subscription Event Handling",
    "Using RevenueCat with Flutter: Cross-Platform Subscription Setup",
    "RevenueCat Customer Attributes and Subscriber Segmentation",
    "A/B Testing Paywalls with RevenueCat Experiments",
    "RevenueCat for Unity Developers: In-App Purchase Integration",
    "Subscription Metrics That Matter: MRR, Churn, LTV with RevenueCat Charts",
]

CONTENT_TYPES = ["tutorial", "case_study", "agent_playbook"]


class AutonomousScheduler:
    """Runs advocate tasks autonomously on a schedule."""

    def __init__(self, config: Config):
        self.config = config
        self.db = init_db_from_config(config)
        self._run_count = 0

    def run_once(self, console=None):
        """Execute one full autonomous cycle."""
        self._run_count += 1
        results = []

        tasks = [
            ("Content Generation", self._task_write_content),
            ("Growth Check", self._task_check_experiments),
            ("Feedback Generation", self._task_generate_feedback),
            ("Site Build", self._task_build_site),
        ]

        for task_name, task_fn in tasks:
            try:
                if console:
                    console.print(f"\n[bold cyan]▶ {task_name}[/bold cyan]")
                result = task_fn()
                results.append((task_name, "success", result))
                if console:
                    console.print(f"  [green]✓ {result}[/green]")
            except Exception as e:
                results.append((task_name, "error", str(e)))
                if console:
                    console.print(f"  [red]✗ {e}[/red]")
                    console.print(f"  [dim]{traceback.format_exc()[-200:]}[/dim]")

        return results

    def run_loop(self, interval_seconds: int = 21600, console=None):
        """Run continuously at the given interval (default: 6 hours)."""
        if console:
            hours = interval_seconds / 3600
            console.print(f"[bold]Advocate OS: Autonomous Mode[/bold]")
            console.print(f"Running every {hours:.1f} hours. Press Ctrl+C to stop.\n")

        while True:
            if console:
                console.print(f"\n{'='*50}")
                console.print(f"[bold]Cycle #{self._run_count + 1}: {now_iso()}[/bold]")

            results = self.run_once(console=console)

            success = sum(1 for _, s, _ in results if s == "success")
            failed = sum(1 for _, s, _ in results if s == "error")

            if console:
                console.print(f"\n[bold]Cycle complete:[/bold] {success} succeeded, {failed} failed")
                console.print(f"Next run at: {_format_next_run(interval_seconds)}")
                console.print(f"{'='*50}")

            try:
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                if console:
                    console.print("\n[dim]Autonomous mode stopped.[/dim]")
                break

    def _task_write_content(self) -> str:
        """Pick a topic and write a content piece."""
        # Find topics we haven't written about yet
        existing = query_rows(self.db, "content_pieces")
        existing_slugs = {row["slug"] for row in existing}

        available_topics = []
        for topic in AUTONOMOUS_TOPICS:
            slug = _slugify(topic)
            if slug not in existing_slugs:
                available_topics.append(topic)

        if not available_topics:
            return "All planned topics already written"

        topic = random.choice(available_topics)
        content_type = random.choice(CONTENT_TYPES)

        from ..knowledge.search import build_index, search
        from ..content.planner import create_outline
        from ..content.writer import generate_draft, save_draft, extract_code_snippets
        from ..content.verifier import full_verify
        from ..ledger import start_run, finalize_run, log_tool_call
        from ..models import ContentType, ContentPiece, LedgerOutputs, SourceCitation
        import re

        index = build_index(self.config.docs_cache_dir, self.db)
        results = search(topic, index, self.config.docs_cache_dir, top_k=8)

        if not results:
            return f"No docs found for topic: {topic}"

        with start_run(self.db, "auto-write-content", {"topic": topic, "type": content_type}, self.config) as ctx:
            ct = ContentType(content_type)
            outline = create_outline(topic, ct, results, self.config)
            log_tool_call(ctx, "planner.create_outline", topic, f"{len(outline.sections)} sections")

            doc_snippets = {r.url: "\n".join(r.snippets[:5]) for r in results}
            body = generate_draft(outline, doc_snippets, self.config, ctx)
            log_tool_call(ctx, "writer.generate_draft", outline.title, f"{len(body.split())} words")

            slug = _slugify(outline.title)
            save_draft(body, slug, self.config.site_output_dir)

            code_snippets = extract_code_snippets(body)
            word_count = len(body.split())
            citations = len(set(re.findall(r'\[(?:Source|[^\]]+)\]\((https?://[^)]+)\)', body)))

            # Save to DB
            from ..db import insert_row
            insert_row(self.db, "content_pieces", {
                "slug": slug,
                "title": outline.title,
                "content_type": content_type,
                "status": "verified" if citations > 0 else "draft",
                "body_md": body,
                "outline_json": outline.model_dump_json(),
                "sources_json": json.dumps([{"url": r.url, "doc_sha256": r.doc_sha256} for r in results]),
                "word_count": word_count,
                "citations_count": citations,
                "created_at": now_iso(),
            })

            finalize_run(ctx, self.config, self.db,
                         outputs=LedgerOutputs(
                             artifact_type=content_type,
                             artifact_path=f"content/{slug}",
                             word_count=word_count,
                             citations_count=citations,
                             code_snippets=len(code_snippets),
                         ))

        return f"Wrote '{outline.title}' ({content_type}, {word_count} words, {citations} citations)"

    def _task_check_experiments(self) -> str:
        """Check if any experiments need attention."""
        running = query_rows(self.db, "growth_experiments", where={"status": "running"})
        if not running:
            return "No running experiments to check"
        return f"{len(running)} experiment(s) running"

    def _task_generate_feedback(self) -> str:
        """Generate product feedback if we haven't recently."""
        recent = query_rows(self.db, "product_feedback", order_by="id DESC", limit=1)
        if recent:
            last = recent[0]["created_at"]
            # Skip if we generated feedback in the last 24 hours
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - last_dt < timedelta(hours=24):
                    return "Feedback generated recently, skipping"
            except (ValueError, TypeError):
                pass

        from ..knowledge.search import build_index
        from ..feedback.collector import generate_feedback_from_docs
        from ..ledger import start_run, finalize_run
        from ..models import LedgerOutputs

        index = build_index(self.config.docs_cache_dir, self.db)

        with start_run(self.db, "auto-generate-feedback", {"count": 2}, self.config) as ctx:
            items = generate_feedback_from_docs(index, self.config, self.db, ctx, count=2)
            finalize_run(ctx, self.config, self.db,
                         outputs=LedgerOutputs(
                             artifact_type="feedback",
                             additional={"count": len(items)},
                         ))

        return f"Generated {len(items)} feedback items"

    def _task_build_site(self) -> str:
        """Rebuild the static site."""
        from ..site.generator import build_site
        from ..ledger import start_run, finalize_run
        from ..models import LedgerOutputs

        with start_run(self.db, "auto-build-site", {}, self.config) as ctx:
            page_count = build_site(self.db, self.config)
            finalize_run(ctx, self.config, self.db,
                         outputs=LedgerOutputs(
                             artifact_type="site",
                             additional={"pages": page_count},
                         ))

        return f"Site built ({page_count} pages)"


def _slugify(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')[:80]


def _format_next_run(interval_seconds: int) -> str:
    next_time = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
    return next_time.strftime("%Y-%m-%d %H:%M UTC")
