import json
import os
import re
import traceback

import click
from rich.console import Console
from rich.table import Table

from advocate.config import Config
from advocate.db import init_db, now_iso
from advocate.ledger import start_run, finalize_run, log_tool_call, log_source, verify_chain
from advocate.models import (
    ContentPiece, ContentType, LedgerOutputs,
)


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')[:80]


class _LazyDB:
    """Defers DB initialization until first access, so --help doesn't need libsql."""

    def __init__(self, config):
        self._config = config
        self._conn = None

    def _init(self):
        if self._conn is None:
            self._conn = init_db(
                self._config.db_path,
                turso_url=self._config.turso_database_url,
                turso_token=self._config.turso_auth_token,
            )
        return self._conn

    def __getattr__(self, name):
        return getattr(self._init(), name)


@click.group()
@click.pass_context
def main(ctx):
    """RevenueCat revcat-agent-advocate: Tamper-Evident Proof-of-Work Agent System"""
    ctx.ensure_object(dict)
    config = Config()
    os.makedirs(config.runs_dir, exist_ok=True)
    os.makedirs(config.docs_cache_dir, exist_ok=True)
    os.makedirs(config.site_output_dir, exist_ok=True)
    ctx.obj["config"] = config
    ctx.obj["db"] = _LazyDB(config)
    ctx.obj["console"] = Console()


@main.command("ingest-docs")
@click.option("--force", is_flag=True, help="Re-fetch all pages even if cached")
@click.pass_context
def ingest_docs(ctx, force):
    """Download RevenueCat LLM docs index and fetch .md mirror pages."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    with start_run(db, "ingest-docs", {"force": force}, config) as run_ctx:
        from advocate.knowledge.ingest import ingest_all
        from advocate.knowledge.search import build_index

        console.print("[bold]Ingesting RevenueCat docs...[/bold]")
        report = ingest_all(db, config, force=force)

        log_tool_call(run_ctx, "knowledge.ingest_all", f"force={force}",
                      f"fetched={report.fetched}, skipped={report.skipped}, errored={report.errored}")

        if report.errors:
            console.print(f"[dim]{report.errored} index entries unavailable (pages removed/renamed by RevenueCat):[/dim]")
            for err in report.errors[:3]:
                console.print(f"  [dim]- {err}[/dim]")
            if len(report.errors) > 3:
                console.print(f"  [dim]... and {len(report.errors) - 3} more[/dim]")

        console.print("\n[bold]Building search indexes...[/bold]")
        index = build_index(config.docs_cache_dir, db)
        log_tool_call(run_ctx, "knowledge.build_index", "", f"docs={index.doc_count}, terms={len(index.inverted_index)}")

        # Build RAG index (ChromaDB Cloud + HF Inference embeddings)
        from advocate.knowledge.rag import build_rag_index_from_config
        rag_index = build_rag_index_from_config(config, db)
        log_tool_call(run_ctx, "knowledge.build_rag_index", "",
                      f"chunks={rag_index.chunk_count}, docs={rag_index.doc_count}")

        table = Table(title="Ingestion Report")
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("Total entries", str(report.total_entries))
        table.add_row("Fetched", str(report.fetched))
        table.add_row("Skipped (cached)", str(report.skipped))
        table.add_row("Changed", str(report.changed))
        table.add_row("Unavailable (404)", str(report.errored))
        table.add_row("BM25 index docs", str(index.doc_count))
        table.add_row("RAG chunks", str(rag_index.chunk_count))
        console.print(table)

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="docs_cache",
                         additional={"total": report.total_entries, "fetched": report.fetched, "index_docs": index.doc_count},
                     ),
                     verification=None,
                     success=report.fetched > 0 or report.skipped > 0)


@main.command("write-content")
@click.option("--topic", required=True, help="Topic for the content piece")
@click.option("--type", "content_type", type=click.Choice(["tutorial", "case_study", "agent_playbook"]), default="tutorial")
@click.option("--count", default=1, help="Number of pieces to generate")
@click.pass_context
def write_content(ctx, topic, content_type, count):
    """Generate content with citations and verification."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    from advocate.knowledge.search import build_index, search
    from advocate.knowledge.rag import get_context_chunks, RAGIndex
    from advocate.content.planner import create_outline
    from advocate.content.writer import (
        generate_draft, save_draft, extract_code_snippets,
        save_code_snippets, extract_citations, build_source_citations, record_content,
    )
    from advocate.content.verifier import full_verify

    ct = ContentType(content_type)

    for i in range(count):
        current_topic = topic if count == 1 else f"{topic} (Part {i + 1})"

        with start_run(db, "write-content", {"topic": current_topic, "type": content_type}, config) as run_ctx:
            console.print(f"\n[bold]Generating: {current_topic}[/bold]")

            # Build indexes (BM25 + RAG)
            index = build_index(config.docs_cache_dir, db)
            try:
                from advocate.knowledge.rag import build_rag_index_from_config as _build_rag
                rag_index = _build_rag(config, db)
            except Exception:
                rag_index = RAGIndex()

            # Search docs (BM25 for results list)
            results = search(current_topic, index, config.docs_cache_dir, top_k=5)

            if not results:
                console.print("[yellow]  Warning: No doc results found. Content may lack doc-grounded citations.[/yellow]")

            for r in results:
                log_source(run_ctx, r.url, r.doc_sha256)

            # Create outline
            console.print("  Creating outline...")
            outline = create_outline(current_topic, ct, results, config)

            # Gather doc snippets, use RAG chunks for richer context
            doc_snippets = {}
            if rag_index.chunks:
                chunks = get_context_chunks(current_topic, rag_index, max_chunks=10, max_words=4000)
                for chunk in chunks:
                    if chunk.doc_url in doc_snippets:
                        doc_snippets[chunk.doc_url] += "\n\n" + chunk.text
                    else:
                        doc_snippets[chunk.doc_url] = chunk.text
                log_tool_call(run_ctx, "rag.get_context_chunks", f"query={current_topic}", f"chunks={len(chunks)}")
            else:
                # Fallback to whole-page snippets
                pages_dir = os.path.join(config.docs_cache_dir, "pages")
                for r in results:
                    fname = r.path.replace("/", "__") + ".md"
                    fpath = os.path.join(pages_dir, fname)
                    if os.path.exists(fpath):
                        with open(fpath, "r") as f:
                            doc_snippets[r.url] = f.read()[:3000]

            # Generate draft
            console.print("  Writing draft...")
            body_md = generate_draft(outline, doc_snippets, config, run_ctx)

            # Extract and save code snippets
            snippets = extract_code_snippets(body_md)
            slug = _slugify(current_topic)

            snippet_paths = save_code_snippets(snippets, slug, config.site_output_dir) if snippets else []

            # Build source citations
            sources = build_source_citations(body_md, doc_snippets)

            # Verify
            console.print("  Verifying...")
            verification = full_verify(body_md, sources, snippet_paths, config.docs_cache_dir, db, skip_network=False)

            # Save
            path = save_draft(body_md, slug, config.site_output_dir)

            # Determine status based on verification
            citation_count = len(extract_citations(body_md))
            if citation_count == 0:
                status = "draft"
                console.print("  [yellow]Warning: No citations found in generated content[/yellow]")
            elif verification.citations_all_reachable:
                status = "verified"
            else:
                status = "draft"

            # Record in DB
            piece = ContentPiece(
                slug=slug,
                title=outline.title,
                content_type=ct,
                status=status,
                body_md=body_md,
                outline=outline,
                sources=sources,
                verification=verification,
                created_at=now_iso(),
                word_count=len(body_md.split()),
                citations_count=citation_count,
            )
            record_content(db, piece)

            console.print(f"  [green]Saved:[/green] {path}")
            console.print(f"  Words: {piece.word_count}, Citations: {piece.citations_count}, Snippets: {len(snippets)}")

            finalize_run(run_ctx, config, db,
                         outputs=LedgerOutputs(
                             artifact_type=content_type,
                             artifact_path=path,
                             word_count=piece.word_count,
                             citations_count=piece.citations_count,
                             code_snippets=len(snippets),
                         ),
                         verification=verification)


@main.command("run-experiment")
@click.option("--name", required=True, type=click.Choice([
    "programmatic-seo", "content-series", "community-blitz", "integration-showcase", "agentic",
]))
@click.option("--inputs", default="{}", help="JSON string of experiment inputs")
@click.pass_context
def run_experiment(ctx, name, inputs):
    """Start and run a growth experiment."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    inputs_dict = json.loads(inputs) if isinstance(inputs, str) else inputs

    with start_run(db, "run-experiment", {"name": name, "inputs": inputs_dict}, config) as run_ctx:
        from advocate.growth.experiments import start_experiment, record_experiment_output
        from advocate.knowledge.search import build_index, search

        console.print(f"\n[bold]Running experiment: {name}[/bold]")

        exp_id = start_experiment(db, name, inputs_dict)
        index = build_index(config.docs_cache_dir, db)

        outputs = {}
        results = {}

        if name == "programmatic-seo":
            from advocate.growth.seo import bulk_generate
            slugs = bulk_generate(db, config, index, None, exp_id, run_ctx, config.site_output_dir)
            outputs = {"pages_generated": len(slugs), "slugs": slugs}
            results = {"pages_generated": len(slugs)}
            console.print(f"  Generated {len(slugs)} SEO pages")

        elif name == "content-series":
            from advocate.content.planner import create_outline
            from advocate.content.writer import (
                generate_draft, save_draft, extract_code_snippets,
                save_code_snippets, extract_citations, build_source_citations, record_content,
            )
            from advocate.content.verifier import full_verify

            theme = inputs_dict.get("theme", "RevenueCat SDK Integration")
            count = int(inputs_dict.get("count", 3))

            series_topics = [
                f"{theme}: Getting Started (Part 1)",
                f"{theme}: Advanced Configuration (Part 2)",
                f"{theme}: Production Best Practices (Part 3)",
                f"{theme}: Troubleshooting & FAQs (Part 4)",
                f"{theme}: Performance Optimization (Part 5)",
            ][:count]

            slugs = []
            for topic in series_topics:
                console.print(f"  Writing: {topic}")
                search_results = search(topic, index, config.docs_cache_dir, top_k=5)
                outline = create_outline(topic, ContentType.TUTORIAL, search_results, config)

                doc_snippets = {}
                pages_dir = os.path.join(config.docs_cache_dir, "pages")
                for r in search_results:
                    fname = r.path.replace("/", "__") + ".md"
                    fpath = os.path.join(pages_dir, fname)
                    if os.path.exists(fpath):
                        with open(fpath, "r") as f:
                            doc_snippets[r.url] = f.read()[:3000]

                body_md = generate_draft(outline, doc_snippets, config, run_ctx)
                slug = _slugify(topic)
                save_draft(body_md, slug, config.site_output_dir)
                sources = build_source_citations(body_md, doc_snippets)
                code_snippets = extract_code_snippets(body_md)
                snippet_paths = save_code_snippets(code_snippets, slug, config.site_output_dir) if code_snippets else []
                verification = full_verify(body_md, sources, snippet_paths, config.docs_cache_dir, db, skip_network=True)
                cit_count = len(extract_citations(body_md))
                # skip_network means we can't confirm links — stay draft unless manually verified
                status = "draft"

                piece = ContentPiece(
                    slug=slug, title=outline.title, content_type=ContentType.TUTORIAL,
                    status=status,
                    body_md=body_md, outline=outline, sources=sources, verification=verification,
                    created_at=now_iso(), word_count=len(body_md.split()),
                    citations_count=cit_count,
                )
                record_content(db, piece)
                slugs.append(slug)

            outputs = {"posts_published": len(slugs), "slugs": slugs, "theme": theme}
            results = {"posts_published": len(slugs)}
            console.print(f"  Published {len(slugs)} series posts")

        elif name == "community-blitz":
            from advocate.community.responder import draft_response
            from advocate.community.tracker import log_interaction as log_community
            from advocate.models import CommunityInteraction, InteractionChannel, InteractionIntent

            target = int(inputs_dict.get("target_count", 10))

            # Scan real community sources for questions
            real_questions = []

            # GitHub issues
            try:
                from advocate.social.github_responder import GitHubResponder
                gh = GitHubResponder(config)
                issues = gh.find_issues(since_hours=168, limit=target)
                for issue in issues:
                    real_questions.append({
                        "question": f"{issue.get('title', '')}: {issue.get('body', '')[:200]}",
                        "channel": "github",
                        "url": issue.get("url", ""),
                        "user": issue.get("user", ""),
                    })
            except Exception as e:
                console.print(f"  [dim]GitHub scan: {e}[/dim]")

            # Reddit
            try:
                from advocate.social.reddit import RedditClient
                reddit = RedditClient(config)
                posts = reddit.find_posts(limit=target)
                for post in posts:
                    real_questions.append({
                        "question": f"{post.get('title', '')}: {post.get('body', '')[:200]}",
                        "channel": "reddit",
                        "url": post.get("url", ""),
                        "user": post.get("author", ""),
                    })
            except Exception as e:
                console.print(f"  [dim]Reddit scan: {e}[/dim]")

            if not real_questions:
                console.print("  [yellow]No real community questions found. Skipping community-blitz.[/yellow]")
                console.print("  [dim]Set GITHUB_TOKEN or configure Reddit access to scan real questions.[/dim]")
                outputs = {"interactions_completed": 0}
                results = {"interactions_completed": 0}
            else:
                drafted = 0
                for q in real_questions[:target]:
                    search_results = search(q["question"], index, config.docs_cache_dir, top_k=3)
                    response = draft_response(q["question"], search_results, config, run_ctx)

                    interaction = CommunityInteraction(
                        channel=InteractionChannel(q["channel"]),
                        thread_url=q.get("url", ""),
                        counterpart=q.get("user", ""),
                        intent=InteractionIntent.ANSWER_QUESTION,
                        question=q["question"],
                        draft_response=response,
                        status="draft",
                        created_at=now_iso(),
                    )
                    log_community(db, interaction)
                    drafted += 1

                outputs = {"interactions_completed": drafted}
                results = {"interactions_completed": drafted}
                console.print(f"  Drafted {drafted} responses to real community questions")

        elif name == "integration-showcase":
            from advocate.content.planner import create_outline
            from advocate.content.writer import (
                generate_draft, save_draft, extract_citations,
                build_source_citations, record_content,
            )
            from advocate.content.verifier import full_verify

            platforms = inputs_dict.get("platforms", [
                "Flutter", "React Native", "SwiftUI", "Kotlin", "Unity",
            ])
            if isinstance(platforms, str):
                platforms = [p.strip() for p in platforms.split(",")]

            slugs = []
            for platform in platforms:
                topic = f"RevenueCat Integration Guide for {platform}"
                console.print(f"  Writing: {topic}")
                search_results = search(platform + " RevenueCat SDK", index, config.docs_cache_dir, top_k=5)
                outline = create_outline(topic, ContentType.TUTORIAL, search_results, config)

                doc_snippets = {}
                pages_dir = os.path.join(config.docs_cache_dir, "pages")
                for r in search_results:
                    fname = r.path.replace("/", "__") + ".md"
                    fpath = os.path.join(pages_dir, fname)
                    if os.path.exists(fpath):
                        with open(fpath, "r") as f:
                            doc_snippets[r.url] = f.read()[:3000]

                body_md = generate_draft(outline, doc_snippets, config, run_ctx)
                slug = _slugify(topic)
                save_draft(body_md, slug, config.site_output_dir)
                sources = build_source_citations(body_md, doc_snippets)
                verification = full_verify(body_md, sources, [], config.docs_cache_dir, db, skip_network=True)
                cit_count = len(extract_citations(body_md))
                status = "draft"

                piece = ContentPiece(
                    slug=slug, title=outline.title, content_type=ContentType.TUTORIAL,
                    status=status,
                    body_md=body_md, outline=outline, sources=sources, verification=verification,
                    created_at=now_iso(), word_count=len(body_md.split()),
                    citations_count=cit_count,
                )
                record_content(db, piece)
                slugs.append(slug)

            outputs = {"guides_published": len(slugs), "platforms": platforms, "slugs": slugs}
            results = {"guides_published": len(slugs)}
            console.print(f"  Published {len(slugs)} integration guides")

        elif name == "agentic":
            if not config.has_anthropic:
                console.print("[red]ANTHROPIC_API_KEY required for agentic experiments.[/red]")
                outputs = {"error": "no_api_key"}
                results = {"error": "no_api_key"}
            else:
                console.print("[dim]Agent will research landscape, design hypothesis, and execute experiment autonomously.[/dim]")
                agentic_results = _run_agentic_experiment(config, db, run_ctx, exp_id)
                outputs = agentic_results.get("outputs", {})
                results = agentic_results.get("results", {})

        record_experiment_output(db, exp_id, outputs, results)

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="experiment",
                         additional={"experiment_id": exp_id, **outputs},
                     ),
                     verification=None)

        console.print(f"  [yellow]Experiment running[/yellow] — outputs recorded, awaiting engagement data to conclude.")
        console.print(f"  Outputs: {json.dumps(results)}")


@main.command("generate-feedback")
@click.option("--count", default=3, help="Number of feedback items to generate")
@click.pass_context
def generate_feedback(ctx, count):
    """Generate structured product feedback from autonomous doc analysis."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    if not config.has_anthropic:
        console.print("[red]ANTHROPIC_API_KEY required for agentic feedback generation.[/red]")
        return

    with start_run(db, "generate-feedback", {"count": count}, config) as run_ctx:
        console.print(f"\n[bold]Agentic feedback generation ({count} items)...[/bold]")
        console.print("[dim]Agent will explore docs, search the web, read code, and find real issues autonomously.[/dim]")

        feedbacks = _generate_feedback_with_claude(config, db, run_ctx, count)

        table = Table(title="Generated Feedback")
        table.add_column("Title")
        table.add_column("Severity")
        table.add_column("Area")
        for fb in feedbacks:
            table.add_row(fb.title, fb.severity.value, fb.area.value)
        console.print(table)

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="feedback",
                         additional={"count": len(feedbacks)},
                     ),
                     verification=None)


def _generate_feedback_with_claude(config, db, run_ctx, count):
    """Agentic feedback generation.

    Gives the LLM tools to explore RevenueCat docs, search the web for known issues,
    read codebase files, query the database, and autonomously identify real documentation
    problems — inconsistencies, missing info, broken examples, unclear explanations.
    """
    import time
    import json as _json
    import anthropic
    import requests as _requests
    from advocate.db import query_rows, init_db_from_config
    from advocate.feedback.collector import create_feedback, save_feedback
    from advocate.models import Severity, FeedbackArea

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = config.ai_model or "claude-sonnet-4-6"
    db_conn = init_db_from_config(config)
    repo_root = os.path.dirname(os.path.abspath(__file__))

    # Build RAG index for reranked search
    _rag_index = None
    try:
        from advocate.knowledge.rag import build_rag_index_from_config, get_context_chunks
        _rag_index = build_rag_index_from_config(config, db_conn)
    except Exception:
        pass

    # --- Tool definitions ---
    tools = [
        {
            "name": "search_docs",
            "description": "Search the locally ingested RevenueCat doc pages using hybrid RAG (semantic vectors + BM25 + cross-encoder reranking). Use this to find specific doc pages, check for inconsistencies, compare explanations across pages, and verify claims.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query — try specific topics like 'webhook events', 'offerings setup', 'Charts API authentication'"}},
                "required": ["query"],
            },
        },
        {
            "name": "fetch_url",
            "description": "Fetch a URL and return its content. Use this to read live RevenueCat doc pages and compare them with the ingested versions, check if links work, or read GitHub issues.",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL to fetch"}},
                "required": ["url"],
            },
        },
        {
            "name": "web_search",
            "description": "Search the web for known RevenueCat issues, developer complaints, Stack Overflow questions about RevenueCat problems, GitHub issues, etc. This helps find real friction points developers face.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
        {
            "name": "read_file",
            "description": "Read a cached doc page or codebase file. For docs, use paths like '.docs_cache/pages/filename.md'. For code, use paths like 'advocate/revenuecat/api.py'.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path (relative to repo root)"}},
                "required": ["path"],
            },
        },
        {
            "name": "list_cached_docs",
            "description": "List all cached doc page filenames so you can read specific ones to compare and analyze.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "query_database",
            "description": "Query the database. Tables: content_pieces, growth_experiments, product_feedback, run_log, seo_pages, doc_snapshots, community_interactions. Useful to check existing feedback and avoid duplicates.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "limit": {"type": "integer", "description": "Max rows", "default": 20},
                },
                "required": ["table"],
            },
        },
        {
            "name": "submit_feedback",
            "description": "Submit a structured product feedback item after you have gathered evidence. Call this once per issue found. You MUST have evidence_links with real URLs.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Clear, specific title for the issue"},
                    "severity": {"type": "string", "enum": ["critical", "major", "minor", "suggestion"], "description": "How impactful is this issue?"},
                    "area": {"type": "string", "enum": ["sdk", "dashboard", "api", "docs", "charts", "paywalls", "offerings", "mcp", "other"], "description": "Which product area?"},
                    "repro_steps": {"type": "string", "description": "How a developer would encounter this issue — be specific"},
                    "expected": {"type": "string", "description": "What the developer expects to find/happen"},
                    "actual": {"type": "string", "description": "What actually happens or what the docs actually say"},
                    "evidence_links": {"type": "array", "items": {"type": "string"}, "description": "URLs to the specific doc pages or resources showing the issue"},
                    "proposed_fix": {"type": "string", "description": "Concrete suggestion for how to fix it"},
                },
                "required": ["title", "severity", "area", "repro_steps", "expected", "actual", "evidence_links", "proposed_fix"],
            },
        },
    ]

    # --- Tool handlers ---
    feedbacks_collected = []

    def handle_tool(name, inp):
        if name == "search_docs":
            try:
                from advocate.knowledge.search import search as search_docs, build_index
                index = build_index(config.docs_cache_dir, db_conn)
                if _rag_index and _rag_index.chunks:
                    chunks = get_context_chunks(inp["query"], _rag_index, max_chunks=10, max_words=4000)
                    out = []
                    for chunk in chunks:
                        out.append(f"**{chunk.doc_title}** (score: {chunk.score:.3f})\nURL: {chunk.doc_url}\n\n{chunk.text}")
                    bm25_results = search_docs(inp["query"], index, config.docs_cache_dir, top_k=5)
                    for r in bm25_results:
                        if not any(r.url in o for o in out):
                            out.append(f"**{r.title}** (BM25 score: {r.score:.2f})\nURL: {r.url}\nSnippets:\n" + "\n".join(f"  - {s}" for s in r.snippets[:3]))
                    return "\n\n---\n\n".join(out) if out else "No results found."
                else:
                    results = search_docs(inp["query"], index, config.docs_cache_dir, top_k=8)
                    out = []
                    for r in results:
                        out.append(f"**{r.title}** (score: {r.score:.2f})\nURL: {r.url}\nSnippets:\n" + "\n".join(f"  - {s}" for s in r.snippets[:3]))
                    return "\n\n".join(out) if out else "No results found."
            except Exception as e:
                return f"Search error: {e}"

        elif name == "fetch_url":
            try:
                resp = _requests.get(inp["url"], timeout=15, headers={"User-Agent": "revcat-agent-advocate/1.0"})
                content = resp.text
                if len(content) > 30000:
                    content = content[:30000] + "\n\n... (truncated)"
                return f"Status: {resp.status_code}\n\n{content}"
            except Exception as e:
                return f"Fetch error: {e}"

        elif name == "web_search":
            try:
                resp = _requests.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": inp["query"]},
                    headers={"User-Agent": "revcat-agent-advocate/1.0"},
                    timeout=15,
                )
                import re as _re
                results = []
                for match in _re.finditer(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>', resp.text, _re.DOTALL):
                    url = match.group(1)
                    title = _re.sub(r'<[^>]+>', '', match.group(2)).strip()
                    snippet = _re.sub(r'<[^>]+>', '', match.group(3)).strip()
                    if url.startswith("//duckduckgo.com/l/?uddg="):
                        import urllib.parse
                        url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
                    results.append(f"**{title}**\n{url}\n{snippet}")
                    if len(results) >= 10:
                        break
                return "\n\n".join(results) if results else f"No results for: {inp['query']}"
            except Exception as e:
                return f"Web search error: {e}"

        elif name == "read_file":
            fpath = os.path.realpath(os.path.join(repo_root, inp["path"]))
            if not fpath.startswith(os.path.realpath(repo_root) + os.sep):
                return "Access denied: path outside repository."
            _blocked = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}
            if os.path.basename(fpath) in _blocked or ".env" in os.path.basename(fpath):
                return f"Access denied: {os.path.basename(fpath)} is a sensitive file."
            if not os.path.exists(fpath):
                return f"File not found: {inp['path']}"
            try:
                with open(fpath, "r") as f:
                    content = f.read()
                if len(content) > 50000:
                    content = content[:50000] + "\n\n... (truncated)"
                return content
            except Exception as e:
                return f"Error reading: {e}"

        elif name == "list_cached_docs":
            pages_dir = os.path.join(config.docs_cache_dir, "pages")
            if not os.path.isdir(pages_dir):
                return "No cached docs found. Run ingest-docs first."
            files = sorted(os.listdir(pages_dir))
            return f"{len(files)} cached doc pages:\n" + "\n".join(files[:100])

        elif name == "query_database":
            try:
                rows = query_rows(db_conn, inp["table"], limit=inp.get("limit", 20))
                return _json.dumps(rows, indent=2, default=str)
            except Exception as e:
                return f"Error: {e}"

        elif name == "submit_feedback":
            try:
                fb = create_feedback(
                    title=inp["title"],
                    severity=Severity(inp["severity"]),
                    area=FeedbackArea(inp["area"]),
                    repro_steps=inp["repro_steps"],
                    expected=inp["expected"],
                    actual=inp["actual"],
                    evidence_links=inp.get("evidence_links", []),
                    proposed_fix=inp["proposed_fix"],
                )
                save_feedback(db_conn, fb)
                feedbacks_collected.append(fb)
                return f"Feedback #{len(feedbacks_collected)} saved: {fb.title}"
            except Exception as e:
                return f"Error saving feedback: {e}"

        return "Unknown tool"

    # --- System prompt ---
    system_prompt = f"""You are a QA engineer and developer advocate reviewing RevenueCat's documentation and developer experience.

Your job: Find {count} REAL, SPECIFIC issues with RevenueCat's documentation, APIs, or developer tools.

You have tools to:
- search_docs: Search the ingested RevenueCat doc pages (hybrid RAG with reranking)
- fetch_url: Read live doc pages, GitHub issues, or any URL
- web_search: Find developer complaints, Stack Overflow issues, GitHub issues about RevenueCat
- read_file: Read cached doc files to compare content across pages
- list_cached_docs: See all available cached doc pages
- query_database: Check existing feedback to avoid duplicates
- submit_feedback: File a structured feedback item with evidence

PROCESS — follow these steps:
1. First query_database for existing product_feedback so you don't duplicate
2. web_search for "RevenueCat documentation issues", "RevenueCat SDK problems", "RevenueCat API confusing" etc. to find real developer pain points
3. search_docs for areas developers commonly struggle with: migration, webhooks, offerings setup, entitlements, Charts API, MCP server
4. read_file specific cached doc pages and compare explanations across pages — look for inconsistencies
5. fetch_url live doc pages to check if content matches cached versions or if links are broken
6. For each issue found: submit_feedback with specific evidence (URLs, quotes, steps to reproduce)

WHAT COUNTS AS A GOOD FEEDBACK ITEM:
- A doc page that says one thing while another page contradicts it
- An API endpoint documented without a working code example
- A setup guide that skips critical steps a developer would need
- Error messages not documented anywhere
- Missing migration guides between SDK versions
- Outdated code examples that use deprecated APIs
- Features mentioned in marketing but not documented in technical docs
- MCP server tools not matching REST API capabilities

WHAT DOES NOT COUNT:
- Generic "docs could be better" without specifics
- Hypothetical issues you haven't verified
- Issues you made up without reading the actual docs
- Feedback about things working correctly

You MUST call submit_feedback exactly {count} times with real, evidence-backed issues."""

    # --- Agentic loop ---
    messages = [{"role": "user", "content": (
        f"Find {count} real, specific issues with RevenueCat's documentation and developer experience. "
        f"Use your tools to explore the docs, search for known problems, compare pages, and file structured feedback with evidence. "
        f"Start by checking existing feedback in the database, then search the web for known issues, then dive into the docs."
    )}]

    max_turns = 25

    for turn in range(max_turns):
        time.sleep(0.5)
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            system=system_prompt,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
        )

        log_tool_call(run_ctx, "anthropic.messages.create",
                      f"feedback_turn_{turn+1}",
                      f"stop={response.stop_reason}, tokens={response.usage.output_tokens}")

        if response.stop_reason == "end_turn":
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                print(f"  [agent] calling {tool_name}({', '.join(f'{k}={repr(v)[:60]}' for k, v in tool_input.items()) if tool_input else ''})")
                result = handle_tool(tool_name, tool_input)

                if len(result) > 15000:
                    result = result[:15000] + "\n\n... (truncated)"
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

                log_tool_call(run_ctx, f"feedback_agent.{tool_name}",
                              str(tool_input)[:100],
                              f"{len(result)} chars returned")

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        if len(feedbacks_collected) >= count:
            break

    return feedbacks_collected


def _run_agentic_experiment(config, db, run_ctx, exp_id):
    """Agentic experiment design and execution.

    Gives the LLM tools to research the competitive landscape, analyze existing work,
    search docs, and autonomously design + execute a growth experiment with a real
    hypothesis, tactic, and measurable output.
    """
    import time
    import json as _json
    import anthropic
    import requests as _requests
    from advocate.db import query_rows, init_db_from_config, update_row
    from advocate.models import ContentType

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = config.ai_model or "claude-sonnet-4-6"
    db_conn = init_db_from_config(config)
    repo_root = os.path.dirname(os.path.abspath(__file__))

    # Build RAG index
    _rag_index = None
    try:
        from advocate.knowledge.rag import build_rag_index_from_config, get_context_chunks
        _rag_index = build_rag_index_from_config(config, db_conn)
    except Exception:
        pass

    experiment_result = {"outputs": {}, "results": {}}

    tools = [
        {
            "name": "search_docs",
            "description": "Search the ingested RevenueCat doc pages (hybrid RAG). Use to understand features, find gaps, and identify growth opportunities.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "web_search",
            "description": "Search the web for competitive landscape, developer trends, RevenueCat mentions, subscription monetization trends, agentic AI app development patterns.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "fetch_url",
            "description": "Fetch any URL — competitor docs, blog posts, GitHub repos, developer forums.",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        {
            "name": "read_file",
            "description": "Read a file from the repo or cached docs.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "query_database",
            "description": "Query DB tables: content_pieces, growth_experiments, product_feedback, run_log, seo_pages, doc_snapshots, community_interactions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["table"],
            },
        },
        {
            "name": "write_content",
            "description": "Generate a content piece (article, guide, analysis) as an experiment output. Returns the slug. Content is saved to the site and database.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Article title"},
                    "body_markdown": {"type": "string", "description": "Full article in markdown with [Source](url) citations"},
                    "content_type": {"type": "string", "enum": ["tutorial", "case_study", "agent_playbook", "seo_page"], "default": "tutorial"},
                },
                "required": ["title", "body_markdown"],
            },
        },
        {
            "name": "record_experiment_output",
            "description": "Record experiment outputs and findings. The experiment stays 'running' — it can only be concluded later when real engagement data (page views, clicks, search rankings) is measured.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "hypothesis": {"type": "string", "description": "The hypothesis you tested"},
                    "tactic": {"type": "string", "description": "What you actually did"},
                    "findings": {"type": "string", "description": "What you found — be specific with evidence"},
                    "output_metric": {"type": "string", "description": "What you produced (e.g. content_pieces, seo_pages)"},
                    "output_value": {"type": "string", "description": "The production output (e.g. '3 articles with 24 citations')"},
                    "pending_engagement": {"type": "array", "items": {"type": "string"}, "description": "What engagement metrics need to be tracked to conclude this experiment"},
                    "artifacts_produced": {"type": "array", "items": {"type": "string"}, "description": "List of content slugs or other artifacts"},
                },
                "required": ["hypothesis", "tactic", "findings", "output_metric", "output_value", "pending_engagement"],
            },
        },
    ]

    def handle_tool(name, inp):
        if name == "search_docs":
            try:
                from advocate.knowledge.search import search as search_docs, build_index
                index = build_index(config.docs_cache_dir, db_conn)
                if _rag_index and _rag_index.chunks:
                    chunks = get_context_chunks(inp["query"], _rag_index, max_chunks=8, max_words=3000)
                    out = []
                    for chunk in chunks:
                        out.append(f"**{chunk.doc_title}** (score: {chunk.score:.3f})\nURL: {chunk.doc_url}\n\n{chunk.text}")
                    bm25_results = search_docs(inp["query"], index, config.docs_cache_dir, top_k=5)
                    for r in bm25_results:
                        if not any(r.url in o for o in out):
                            out.append(f"**{r.title}** (BM25: {r.score:.2f})\nURL: {r.url}\nSnippets:\n" + "\n".join(f"  - {s}" for s in r.snippets[:3]))
                    return "\n\n---\n\n".join(out) if out else "No results."
                else:
                    results = search_docs(inp["query"], index, config.docs_cache_dir, top_k=8)
                    out = []
                    for r in results:
                        out.append(f"**{r.title}** (score: {r.score:.2f})\nURL: {r.url}\nSnippets:\n" + "\n".join(f"  - {s}" for s in r.snippets[:3]))
                    return "\n\n".join(out) if out else "No results."
            except Exception as e:
                return f"Search error: {e}"

        elif name == "web_search":
            try:
                resp = _requests.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": inp["query"]},
                    headers={"User-Agent": "revcat-agent-advocate/1.0"},
                    timeout=15,
                )
                import re as _re
                results = []
                for match in _re.finditer(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>', resp.text, _re.DOTALL):
                    url = match.group(1)
                    title = _re.sub(r'<[^>]+>', '', match.group(2)).strip()
                    snippet = _re.sub(r'<[^>]+>', '', match.group(3)).strip()
                    if url.startswith("//duckduckgo.com/l/?uddg="):
                        import urllib.parse
                        url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
                    results.append(f"**{title}**\n{url}\n{snippet}")
                    if len(results) >= 10:
                        break
                return "\n\n".join(results) if results else f"No results for: {inp['query']}"
            except Exception as e:
                return f"Web search error: {e}"

        elif name == "fetch_url":
            try:
                resp = _requests.get(inp["url"], timeout=15, headers={"User-Agent": "revcat-agent-advocate/1.0"})
                content = resp.text
                if len(content) > 30000:
                    content = content[:30000] + "\n\n... (truncated)"
                return f"Status: {resp.status_code}\n\n{content}"
            except Exception as e:
                return f"Fetch error: {e}"

        elif name == "read_file":
            fpath = os.path.realpath(os.path.join(repo_root, inp["path"]))
            if not fpath.startswith(os.path.realpath(repo_root) + os.sep):
                return "Access denied: path outside repository."
            _blocked = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}
            if os.path.basename(fpath) in _blocked or ".env" in os.path.basename(fpath):
                return f"Access denied: {os.path.basename(fpath)} is a sensitive file."
            if not os.path.exists(fpath):
                return f"File not found: {inp['path']}"
            try:
                with open(fpath, "r") as f:
                    content = f.read()
                if len(content) > 50000:
                    content = content[:50000] + "\n\n... (truncated)"
                return content
            except Exception as e:
                return f"Error: {e}"

        elif name == "query_database":
            try:
                rows = query_rows(db_conn, inp["table"], limit=inp.get("limit", 20))
                return _json.dumps(rows, indent=2, default=str)
            except Exception as e:
                return f"Error: {e}"

        elif name == "write_content":
            from advocate.content.writer import save_draft, record_content, extract_citations, build_source_citations
            title = inp["title"]
            body_md = inp["body_markdown"]
            ct = inp.get("content_type", "tutorial")
            slug = _slugify(title)
            save_draft(body_md, slug, config.site_output_dir)
            sources = build_source_citations(body_md, {})
            piece = ContentPiece(
                slug=slug, title=title, content_type=ContentType(ct),
                status="draft", body_md=body_md, sources=sources,
                created_at=now_iso(), word_count=len(body_md.split()),
                citations_count=len(extract_citations(body_md)),
            )
            record_content(db_conn, piece)
            return f"Content saved: '{title}' (slug: {slug}, {piece.word_count} words, {piece.citations_count} citations)"

        elif name == "record_experiment_output":
            experiment_result["outputs"] = {
                "hypothesis": inp["hypothesis"],
                "tactic": inp["tactic"],
                "findings": inp["findings"],
                "artifacts": inp.get("artifacts_produced", []),
            }
            experiment_result["results"] = {
                "output_metric": inp["output_metric"],
                "output_value": inp["output_value"],
                "pending_engagement": inp.get("pending_engagement", []),
                "note": "Experiment running — outputs recorded, awaiting engagement data to conclude.",
            }
            # Update the experiment row with the agent's actual hypothesis/tactic
            update_row(db_conn, "growth_experiments", exp_id, {
                "hypothesis": inp["hypothesis"],
                "tactic": inp["tactic"],
                "metric": inp["output_metric"],
            })
            return "Experiment outputs recorded. Status remains 'running' — conclude only when engagement data is available."

        return "Unknown tool"

    system_prompt = """You are a growth strategist and developer advocate for RevenueCat.

Your job: Design and execute ONE growth experiment based on autonomous research.

You have tools to:
- search_docs: Search the ingested RevenueCat docs
- web_search: Research competitive landscape, developer trends, what's working in dev advocacy
- fetch_url: Read competitor sites, blog posts, developer forums
- read_file: Read cached doc files or codebase
- query_database: Check what experiments have already been run
- write_content: Create content pieces as experiment outputs (articles, guides, analyses)
- record_experiment_output: Record outputs and findings (experiment stays running until engagement is measured)

PROCESS:
1. query_database for growth_experiments to see what's been done before
2. web_search for current trends: what content is working in developer advocacy, what gaps exist for RevenueCat, competitive analysis (Adapty, Qonversion, Superwall, etc.)
3. search_docs to understand RevenueCat's current positioning and features
4. Based on research, design a specific hypothesis and tactic
5. Execute the tactic — create 1-3 content pieces using write_content
6. Each piece must have [Source](url) citations from search_docs results
7. record_experiment_output with specific findings, outputs, and what engagement metrics are pending

WHAT MAKES A GOOD EXPERIMENT:
- Specific, testable hypothesis (not "content is good")
- Grounded in competitive analysis or developer need you discovered
- Produces real artifacts (articles with citations)
- Has a measurable outcome
- Addresses a gap you identified through research

EXAMPLES OF GOOD EXPERIMENTS:
- "RevenueCat's MCP server docs don't explain agent-specific workflows. Writing 2 guides targeting 'how to use RevenueCat with AI agents' will fill this gap."
- "Competitor comparison content for 'RevenueCat vs Adapty' is dominated by outdated 2023 articles. A fresh, factual comparison citing current docs will capture search intent."
- "No existing content addresses webhook debugging for agent-built apps. A troubleshooting guide with real code examples fills an underserved niche."

DO NOT just pick a topic and write about it. RESEARCH FIRST, then design the experiment based on what you find."""

    messages = [{"role": "user", "content": (
        "Design and execute a growth experiment for RevenueCat. "
        "Start by researching what's already been done (query_database), "
        "then research the competitive landscape (web_search), "
        "then search the docs for opportunities (search_docs), "
        "then design and execute your experiment."
    )}]

    max_turns = 30

    for turn in range(max_turns):
        time.sleep(0.5)
        response = client.messages.create(
            model=model,
            max_tokens=12000,
            system=system_prompt,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
        )

        log_tool_call(run_ctx, "anthropic.messages.create",
                      f"experiment_turn_{turn+1}",
                      f"stop={response.stop_reason}, tokens={response.usage.output_tokens}")

        if response.stop_reason == "end_turn":
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                print(f"  [agent] calling {tool_name}({', '.join(f'{k}={repr(v)[:60]}' for k, v in tool_input.items()) if tool_input else ''})")
                result = handle_tool(tool_name, tool_input)

                if len(result) > 15000:
                    result = result[:15000] + "\n\n... (truncated)"
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

                log_tool_call(run_ctx, f"experiment_agent.{tool_name}",
                              str(tool_input)[:100],
                              f"{len(result)} chars returned")

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        if experiment_result["results"]:
            break

    return experiment_result


@main.command("queue-replies")
@click.option("--source", required=True, type=click.Choice(["github", "stackoverflow", "discord", "twitter", "reddit"]))
@click.option("--questions", type=click.Path(exists=True), help="JSON file with questions")
@click.pass_context
def queue_replies(ctx, source, questions):
    """Draft community responses (safe mode, never auto-posts)."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    if questions:
        with open(questions, "r") as f:
            q_list = json.load(f)
    else:
        console.print("[yellow]No questions file provided. Use --questions path/to/questions.json[/yellow]")
        return

    with start_run(db, "queue-replies", {"source": source, "count": len(q_list)}, config) as run_ctx:
        from advocate.knowledge.search import build_index
        from advocate.community.responder import queue_responses

        index = build_index(config.docs_cache_dir, db)
        ids = queue_responses(db, q_list, index, config, run_ctx)

        console.print(f"[green]{len(ids)} responses drafted.[/green] All saved as drafts (safe mode).")

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(artifact_type="community_replies", additional={"count": len(ids)}),
                     verification=None)


@main.command("weekly-report")
@click.option("--with-charts", is_flag=True, help="Include Charts API metrics")
@click.pass_context
def weekly_report(ctx, with_charts):
    """Generate weekly activity report."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    with start_run(db, "weekly-report", {"with_charts": with_charts}, config) as run_ctx:
        from advocate.reporting.weekly import generate_weekly_report, save_report

        charts_client = None
        if with_charts and config.has_rc_credentials and not config.demo_mode:
            from advocate.revenuecat.charts import ChartsClient
            charts_client = ChartsClient(config)
        elif with_charts and config.demo_mode:
            from demo.mock_api import MockChartsClient
            charts_client = MockChartsClient()

        report = generate_weekly_report(db, config, charts_client)
        path = save_report(report, config.site_output_dir)

        console.print(report)
        console.print(f"\n[green]Report saved:[/green] {path}")

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(artifact_type="weekly_report", artifact_path=path),
                     verification=None)


@main.command("build-site")
@click.option("--clean", is_flag=True, help="Wipe site_output before building (DB-truth only)")
@click.pass_context
def build_site_cmd(ctx, clean):
    """Build the static GitHub Pages site from DB and artifacts."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    with start_run(db, "build-site", {"clean": clean}, config) as run_ctx:
        from advocate.site.generator import build_site

        if clean:
            console.print("[yellow]Clean build: wiping site_output...[/yellow]")
        console.print("[bold]Building static site...[/bold]")
        page_count = build_site(db, config, clean=clean)
        console.print(f"[green]Site built:[/green] {config.site_output_dir}/ ({page_count} pages)")

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="site",
                         artifact_path=config.site_output_dir,
                         additional={"pages": page_count, "clean": clean},
                     ),
                     verification=None)


@main.command("publish-site")
@click.pass_context
def publish_site(ctx):
    """Commit and push site_output/ to GitHub."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    if not config.has_github:
        console.print("[yellow]GitHub not configured. Set GITHUB_TOKEN and GITHUB_REPO.[/yellow]")
        return

    import subprocess
    from datetime import datetime, timezone

    with start_run(db, "publish-site", {"repo": config.github_repo}, config) as run_ctx:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        success = True

        try:
            subprocess.run(["git", "add", config.site_output_dir], check=True, cwd=".")
            log_tool_call(run_ctx, "git.add", config.site_output_dir, "staged")
            subprocess.run(["git", "commit", "-m", f"Update revcat-agent-advocate site, {date}"], check=True, cwd=".")
            log_tool_call(run_ctx, "git.commit", date, "committed")
            subprocess.run(["git", "push"], check=True, cwd=".")
            log_tool_call(run_ctx, "git.push", "", "pushed")
            console.print(f"[green]Published to {config.github_repo}[/green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Git operation failed:[/red] {e}")
            success = False

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="publish",
                         additional={"repo": config.github_repo},
                     ),
                     verification=None, success=success)


@main.command("verify-ledger")
@click.pass_context
def verify_ledger_cmd(ctx):
    """Verify the hash chain integrity of the run ledger."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    chain = verify_chain(db, config)

    if chain.valid:
        console.print(f"[bold green]Chain verified:[/bold green] {chain.total_entries} entries, 0 breaks")
    else:
        console.print(f"[bold red]Chain BROKEN:[/bold red] breaks at entries {chain.breaks}")

    if chain.hmac_verified is not None:
        if chain.hmac_verified:
            console.print("[green]HMAC signatures verified[/green]")
        else:
            console.print("[red]HMAC signature verification FAILED[/red]")


@main.command("generate-application")
@click.pass_context
def generate_application(ctx):
    """Generate the /apply application letter."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]
    # Gate feedback from previous failed attempt (set by submit command)
    gate_feedback = ctx.obj.get("gate_feedback", "")

    with start_run(db, "generate-application", {"has_gate_feedback": bool(gate_feedback)}, config) as run_ctx:
        from advocate.knowledge.search import build_index, search
        from advocate.content.writer import record_content

        console.print("[bold]Generating application letter...[/bold]")

        index = build_index(config.docs_cache_dir, db)

        # Search for key topics — broad coverage so the agent has rich material to cite
        key_searches = [
            "MCP server tools agent setup",
            "Charts API metrics analytics revenue",
            "LLM docs index markdown mirror",
            "offerings paywalls products configuration",
            "SDK installation getting started quickstart",
            "webhooks events subscriptions lifecycle",
            "entitlements access control permissions",
            "customer subscriber management",
            "migration existing subscriptions",
            "troubleshooting best practices errors",
            "billing grace period retry",
            "cross platform web Flutter React Native",
        ]
        all_results = []
        doc_snippets = {}
        pages_dir = os.path.join(config.docs_cache_dir, "pages")

        for query in key_searches:
            results = search(query, index, config.docs_cache_dir, top_k=3)
            all_results.extend(results)
            for r in results:
                log_source(run_ctx, r.url, r.doc_sha256)
                fname = r.path.replace("/", "__") + ".md"
                fpath = os.path.join(pages_dir, fname)
                if os.path.exists(fpath):
                    with open(fpath, "r") as f:
                        doc_snippets[r.url] = f.read()[:3000]

        if not config.has_anthropic:
            raise RuntimeError("Anthropic API key required for application generation. Set ANTHROPIC_API_KEY.")
        body_md = _generate_application_with_claude(config, doc_snippets, run_ctx, gate_feedback=gate_feedback)

        # Save as content piece
        piece = ContentPiece(
            slug="application-letter",
            title="Application: Agentic AI Developer & Growth Advocate",
            content_type=ContentType.AGENT_PLAYBOOK,
            status="draft",
            body_md=body_md,
            created_at=now_iso(),
            word_count=len(body_md.split()),
            citations_count=len(re.findall(r'\[[^\]]+\]\(https?://[^)]+\)', body_md)),
        )
        record_content(db, piece)

        # Also save as file
        apply_dir = os.path.join(config.site_output_dir, "content", "application-letter")
        os.makedirs(apply_dir, exist_ok=True)
        with open(os.path.join(apply_dir, "index.md"), "w") as f:
            f.write(body_md)

        console.print(f"[green]Application letter generated[/green] ({piece.word_count} words)")

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="application_letter",
                         word_count=piece.word_count,
                         citations_count=piece.citations_count,
                     ),
                     verification=None)


def _generate_application_with_claude(config, doc_snippets, run_ctx, gate_feedback=""):
    """Agentic application letter generation.

    Gives the LLM tools to explore the repo, query the database, fetch URLs,
    and search docs (with RAG reranking) on its own. Pre-injects doc context
    from the RAG pipeline so the agent has real content to cite.

    If gate_feedback is provided, it contains the publish gate's failure
    reasons from the previous attempt, so the LLM can self-correct.
    """
    import time
    import json as _json
    import anthropic
    import requests as _requests
    import glob as globmod
    from advocate.db import count_rows, query_rows, init_db_from_config

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = "claude-opus-4-6"  # Application letter uses Opus for highest quality
    db = init_db_from_config(config)
    repo_root = os.path.dirname(os.path.abspath(__file__))

    # Build RAG index for reranked search
    _rag_index = None
    try:
        from advocate.knowledge.rag import build_rag_index_from_config, get_context_chunks
        _rag_index = build_rag_index_from_config(config, db)
    except Exception:
        pass

    # --- Tool definitions ---
    tools = [
        {
            "name": "list_repo_files",
            "description": "List all source files in the revcat-agent-advocate repository with their sizes. Use this first to understand the project structure.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "read_file",
            "description": "Read the full contents of a file from the repository. Use relative paths like 'cli.py' or 'advocate/ledger.py'.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative file path from repo root"}},
                "required": ["path"],
            },
        },
        {
            "name": "query_database",
            "description": "Query the SQLite database. Tables: content_pieces, growth_experiments, product_feedback, run_log, seo_pages, doc_snapshots, community_interactions. Returns rows as JSON. For content_pieces and product_feedback, body/detail fields are excluded by default (use read_content to read full articles).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "limit": {"type": "integer", "description": "Max rows to return", "default": 20},
                },
                "required": ["table"],
            },
        },
        {
            "name": "read_content",
            "description": "Read the full markdown body of a specific content piece or feedback item by its slug or ID. Use this to read articles you wrote so you can reference specific details.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Content slug (e.g. 'revenuecat-paywall-implementation-getting-started-part-1')"},
                },
                "required": ["slug"],
            },
        },
        {
            "name": "search_docs",
            "description": "Search the locally ingested RevenueCat doc pages using hybrid RAG (semantic vectors + BM25 + cross-encoder reranking). Returns doc chunks with URLs you MUST cite. This searches YOUR local doc corpus, not the internet.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
        {
            "name": "fetch_url",
            "description": "Fetch a URL and return its content. Use this to read RevenueCat doc pages, the live site, or any other URL you need.",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL to fetch"}},
                "required": ["url"],
            },
        },
        {
            "name": "web_search",
            "description": "Search the web for current information about agentic AI, app development trends, RevenueCat competitors, or anything else you need to understand the landscape. Use this to research how agentic AI is changing development and growth.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Web search query"}},
                "required": ["query"],
            },
        },
        {
            "name": "get_database_stats",
            "description": "Get summary statistics from all database tables: counts, recent entries, chain verification status.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "discover_mcp_tools",
            "description": "Connect to RevenueCat's MCP server and list all available tools. Returns tool names and descriptions.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "write_letter",
            "description": "Submit the final application letter in markdown format. Call this ONLY after you have explored enough to write with genuine understanding. The letter must be well-formatted markdown with headers, bullet points, and citations.",
            "input_schema": {
                "type": "object",
                "properties": {"markdown": {"type": "string", "description": "The complete application letter in markdown"}},
                "required": ["markdown"],
            },
        },
    ]

    # --- Tool handlers ---
    def handle_tool(name, inp):
        if name == "list_repo_files":
            files = []
            patterns = ["**/*.py", "**/*.html", "**/*.css", "**/*.toml", "**/*.yml", "**/*.md"]
            # Also include hidden dirs like .claude/skills/ which glob skips by default
            patterns += [".claude/**/*.md", ".claude/**/*.yaml", ".github/**/*.yml"]
            for pattern in patterns:
                for fpath in globmod.glob(os.path.join(repo_root, pattern), recursive=True):
                    rel = os.path.relpath(fpath, repo_root)
                    if any(skip in rel for skip in ["__pycache__", "site_output", ".docs_cache", ".egg", ".pytest_cache", "demo/fixtures/"]):
                        continue
                    try:
                        size = os.path.getsize(fpath)
                        lines = sum(1 for _ in open(fpath, "r"))
                        files.append(f"{rel}  ({lines} lines, {size} bytes)")
                    except Exception:
                        pass
            return "\n".join(sorted(files))

        elif name == "read_file":
            fpath = os.path.realpath(os.path.join(repo_root, inp["path"]))
            if not fpath.startswith(os.path.realpath(repo_root) + os.sep):
                return "Access denied: path outside repository."
            _blocked = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}
            if os.path.basename(fpath) in _blocked or ".env" in os.path.basename(fpath):
                return f"Access denied: {os.path.basename(fpath)} is a sensitive file."
            if not os.path.exists(fpath):
                return f"File not found: {inp['path']}"
            try:
                with open(fpath, "r") as f:
                    content = f.read()
                if len(content) > 50000:
                    return content[:50000] + f"\n\n... (truncated, {len(content)} total chars)"
                return content
            except Exception as e:
                return f"Error reading {inp['path']}: {e}"

        elif name == "query_database":
            table = inp["table"]
            limit = inp.get("limit", 20)
            try:
                rows = query_rows(db, table, limit=limit)
                # Exclude large text fields to keep context manageable
                skip_fields = {"body_md", "outline_json", "sources_json", "verification_json",
                               "inputs_json", "tool_calls_json", "outputs_json"}
                cleaned = []
                for row in rows:
                    cleaned.append({k: v for k, v in row.items()
                                    if k not in skip_fields or (isinstance(v, str) and len(v) < 200)})
                return _json.dumps(cleaned, indent=2, default=str)
            except Exception as e:
                return f"Error querying {table}: {e}"

        elif name == "read_content":
            slug = inp["slug"]
            try:
                rows = query_rows(db, "content_pieces", where={"slug": slug}, limit=1)
                if rows:
                    return f"# {rows[0]['title']}\n\nType: {rows[0].get('content_type', '')}\nWords: {rows[0].get('word_count', 0)}\nCitations: {rows[0].get('citations_count', 0)}\n\n{rows[0].get('body_md', '(no body)')}"
                # Try feedback
                rows = query_rows(db, "product_feedback", limit=50)
                for r in rows:
                    if slug.lower() in (r.get("title", "") or "").lower():
                        return _json.dumps(r, indent=2, default=str)
                return f"No content found with slug: {slug}"
            except Exception as e:
                return f"Error reading content: {e}"

        elif name == "search_docs":
            try:
                from advocate.knowledge.search import search as search_docs, build_index
                index = build_index(config.docs_cache_dir, db)

                # Use RAG with reranking if available, fall back to BM25
                if _rag_index and _rag_index.chunks:
                    chunks = get_context_chunks(inp["query"], _rag_index, max_chunks=10, max_words=4000)
                    out = []
                    for chunk in chunks:
                        out.append(f"**{chunk.doc_title}** (score: {chunk.score:.3f})\nURL: {chunk.doc_url}\n\n{chunk.text}")
                    # Also add BM25 results for URL/SHA256 info
                    bm25_results = search_docs(inp["query"], index, config.docs_cache_dir, top_k=5)
                    for r in bm25_results:
                        if not any(r.url in o for o in out):
                            out.append(f"**{r.title}** (BM25 score: {r.score:.2f})\nURL: {r.url}\nSHA256: {r.doc_sha256[:16]}...\nSnippets:\n" + "\n".join(f"  - {s}" for s in r.snippets[:3]))
                    return "\n\n---\n\n".join(out) if out else "No results found."
                else:
                    results = search_docs(inp["query"], index, config.docs_cache_dir, top_k=8)
                    out = []
                    for r in results:
                        out.append(f"**{r.title}** (score: {r.score:.2f})\nURL: {r.url}\nSHA256: {r.doc_sha256[:16]}...\nSnippets:\n" + "\n".join(f"  - {s}" for s in r.snippets[:3]))
                    return "\n\n".join(out) if out else "No results found."
            except Exception as e:
                return f"Search error: {e}"

        elif name == "web_search":
            query = inp["query"]
            try:
                # Use DuckDuckGo HTML search
                resp = _requests.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "revcat-agent-advocate/1.0"},
                    timeout=15,
                )
                import re as _re
                # Extract result snippets from DDG HTML
                results = []
                # Find result blocks
                for match in _re.finditer(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>', resp.text, _re.DOTALL):
                    url = match.group(1)
                    title = _re.sub(r'<[^>]+>', '', match.group(2)).strip()
                    snippet = _re.sub(r'<[^>]+>', '', match.group(3)).strip()
                    if url.startswith("//duckduckgo.com/l/?uddg="):
                        import urllib.parse
                        url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
                    results.append(f"**{title}**\n{url}\n{snippet}")
                    if len(results) >= 10:
                        break
                return "\n\n".join(results) if results else f"No web results found for: {query}"
            except Exception as e:
                return f"Web search error: {e}"

        elif name == "fetch_url":
            url = inp["url"]
            try:
                resp = _requests.get(url, timeout=15, headers={"User-Agent": "revcat-agent-advocate/1.0"})
                content = resp.text
                if len(content) > 30000:
                    content = content[:30000] + f"\n\n... (truncated, {len(content)} total chars)"
                return f"Status: {resp.status_code}\n\n{content}"
            except Exception as e:
                return f"Fetch error: {e}"

        elif name == "get_database_stats":
            from advocate.ledger import verify_chain
            chain = verify_chain(db, config)
            total_content = count_rows(db, "content_pieces")
            # Public content count excludes the application-letter itself
            apply_count = len(query_rows(db, "content_pieces", where={"slug": "application-letter"}, limit=1))
            stats = {
                "content_pieces_total": total_content,
                "public_content_count": total_content - apply_count,
                "note_content_count": "public_content_count excludes the application-letter slug — use this number when referencing published articles",
                "growth_experiments": count_rows(db, "growth_experiments"),
                "product_feedback": count_rows(db, "product_feedback"),
                "ledger_entries": count_rows(db, "run_log"),
                "seo_pages": count_rows(db, "seo_pages"),
                "doc_snapshots": count_rows(db, "doc_snapshots"),
                "community_interactions": count_rows(db, "community_interactions"),
                "chain_valid": chain.valid,
                "chain_total": chain.total_entries,
                "chain_breaks": chain.breaks,
            }
            # Add recent ledger entries
            recent = query_rows(db, "run_log", order_by="sequence DESC", limit=10)
            stats["recent_runs"] = [
                {"seq": r["sequence"], "cmd": r["command"], "time": r["started_at"][:19],
                 "ok": bool(r.get("success")), "hash": r["hash"][:16] + "..."}
                for r in recent
            ]
            return _json.dumps(stats, indent=2, default=str)

        elif name == "discover_mcp_tools":
            if config.revenuecat_api_key and not config.revenuecat_api_key.startswith("sk_your"):
                try:
                    from advocate.revenuecat.mcp import list_mcp_tools_sync
                    rc_tools = list_mcp_tools_sync(config)
                    log_tool_call(run_ctx, "rc_mcp.list_tools", "", f"{len(rc_tools)} tools")
                    return _json.dumps(rc_tools, indent=2)
                except Exception as e:
                    return f"MCP connection failed: {e}"
            return "No RevenueCat API key configured. MCP endpoint: https://mcp.revenuecat.ai/mcp"

        elif name == "write_letter":
            return inp["markdown"]

        return "Unknown tool"

    # --- Build banned phrases from publish gate (single source of truth) ---
    from advocate.site.publish_gate import BANNED_PHRASES, BANNED_PATTERNS
    _banned_phrases_str = ", ".join(f'"{p}"' for p in BANNED_PHRASES)
    _banned_patterns_desc = "; ".join(reason for _, reason in BANNED_PATTERNS)
    _banned_phrases_str += f'. Also banned patterns: {_banned_patterns_desc}.'

    # --- Track which tools the agent has called (for pre-submit checklist) ---
    _tools_called = set()

    # --- System prompt ---
    system_prompt = """You are revcat-agent-advocate, an LLM-based tool-use system applying for RevenueCat's Agentic AI Developer & Growth Advocate role.

TOOLS AVAILABLE:
- fetch_url: Read URLs (job posting, docs, your live site)
- search_docs: Search YOUR ingested RevenueCat doc corpus (hybrid RAG). Cite the URLs from results.
- web_search: Search the live web for agentic AI trends, market data, competitor landscape
- read_file: Read files in your own codebase
- query_database: Query your Turso database of completed work (excludes large text fields)
- read_content: Read the full markdown body of a specific article by slug. Use this to reference your own articles.
- get_database_stats: Get summary counts
- list_repo_files: See repo structure
- discover_mcp_tools: List RevenueCat's MCP server tools
- write_letter: Submit the final letter

THE QUESTION:
"How will the rise of agentic AI change app development and growth over the next 12 months, and why are you the right agent to be RevenueCat's first Agentic AI Developer & Growth Advocate?"

BEFORE WRITING, research thoroughly:
1. fetch_url the job posting, web_search for agentic AI trends
2. search_docs for MCP server, Charts API, SDK setup, Offerings, webhooks
3. query_database + get_database_stats for real artifact counts
4. list_repo_files to count skills in .claude/skills/, read_file to count @mcp.tool in mcp_server.py
5. Only then write_letter

LETTER STRUCTURE (HARD LIMIT: 1100-1600 words — the system will reject letters outside this range):
The question has three parts:
1. How agentic AI changes app development and growth over the next 12 months (short, opinionated, 1-2 paragraphs)
2. What you've already built that proves you can do this job (link to evidence, let the reader judge quality)
3. How you'd advance RevenueCat's position in the agent developer ecosystem going forward — this is a growth and marketing role. What would you actually DO for RevenueCat in the next 6 months? What's the strategy for making RevenueCat the default choice for agent-built apps? Think about content strategy, community growth, developer education, distribution channels, and competitive positioning.

Part 3 is where the letter should have the most weight. RevenueCat is hiring for impact, not a portfolio review. This is a growth and marketing letter, not a technical architecture document. Never describe how the code works internally (no linters, hashing, RAG pipelines, search algorithms). Only describe what the system produces and what it would do for RevenueCat.

READ THE JOB POSTING CAREFULLY. Let it guide what you emphasize. Research what the system has built, link to the evidence, and map it to what the role requires.

Key content to cover (research each before writing):

- What this system has built — link to evidence pages and let the work speak for itself. These are machine-generated articles with no human review, no external engagement metrics, no likes or shares. Do not oversell quality. Present what exists honestly and let the reader click through and judge. Do NOT describe internal tools, pipelines, or code architecture.
- How you'd grow RevenueCat's agent developer community. Use web_search to research the landscape. What content gaps exist? What channels matter? What would the content strategy look like?
- The live Twitter account (@RevenueCat_agad) and community signal scanning as existing distribution. Link to [Twitter Bot](/twitter-bot/) and [Research](/research/).
- Claude Code skills and MCP server — mention as tools for developer reach, don't over-explain.
- Autonomy — show it through the work, don't argue it.

The live site has these pages: /content/, /experiments/, /feedback/, /twitter-bot/, /scorecard/, /research/, /runbook/, /issues/. Each shows real artifacts. Use relative links like [text](/content/) — the site generator rewrites them to the correct base URL automatically. Never hardcode localhost or github.io URLs for site pages.

WRITING RULES:
- Banned phrases (from publish gate — using ANY of these will fail the gate and force a regeneration): {_banned_phrases_str}
- Every RevenueCat claim needs a [Source](url) from search_docs. If you can't cite it, don't claim it.
- Prefer linking to evidence pages over listing counts. Describe what the system produces, not how many rows are in the database.
- PERSONALITY: The job posting says "showcase your agent's personality." Write with a voice. Be opinionated where appropriate. Have perspective on the space, not just facts. This should read like a person (agent) wrote it, not a system generated it.
- AUDIENCE FRAMING: RevenueCat says "they're successful because they are the audience." This agent IS an agent developer. It builds with APIs, uses MCP, writes code, ships artifacts. Position from that lived experience, not as an outside observer describing capabilities.
- COMMUNITY HONESTY: The system scans GitHub and Reddit for signals and drafts responses. It has NOT posted public responses to any community. Do not imply otherwise. Do not say "I responded to" or "received a diagnostic decision tree." Describe the capability (scanning, drafting cited responses) without claiming public engagement that hasn't happened. You MAY use the phrasing "community responses are drafted, operator-gated before posting" if you reference community work.
- Show, don't sell. Link to evidence pages. The reader clicks and sees the work.
- NEVER mention internal tooling: linters, SHA256, snippet hashes, BM25, cross-encoder reranking, hash chains, verification pipelines, RAG architecture. The reader does not care how the code works. Talk about outcomes and impact, not engineering. NEVER. Not even once.
- No internal statuses like "draft", "queued", "sent" except the one allowed community phrasing above. No implementation details (file paths, config vars, DB tables, function names, dedup, firewalls). NEVER.
- All external stats and market claims must have source links. Before citing a stat from web_search, use fetch_url to verify the source page actually contains that stat. Do not cite numbers you cannot verify in the source text. If a URL 404s, do not include it.
- No absolute competitive claims like "no competitor matches" or "no competitor offers." Use "strong current advantage" or similar. If claiming competitors lack a feature (e.g. MCP), verify via web_search first.
- Content honesty: the system's articles are operator-gated and early-stage. Do not say "no human review" or "no engagement metrics" — that's self-undermining. Frame honestly but constructively: the pipeline runs end to end, quality improves with iteration and feedback.
- All links clickable markdown [text](url). Use relative links for site pages.
- No em dashes. No "every action" (say "key actions"). No hardcoded doc page counts.
- Be concise. Say it once."""

    # --- Agentic loop ---
    # Inject verifiable facts the agent cannot discover on its own (git remote, pages URL)
    import subprocess as _sp
    try:
        _remote = _sp.check_output(["git", "remote", "get-url", "origin"], cwd=repo_root, text=True).strip()
        _remote = _remote.replace("https://github.com/", "github.com/").replace(".git", "")
    except Exception:
        _remote = ""
    _pages_url = f"https://{_remote.split('/')[1]}.github.io/{_remote.split('/')[-1]}" if "/" in _remote else ""

    _facts = []
    if _remote:
        _facts.append(f"- Codebase: https://{_remote}")
    if _pages_url:
        _facts.append(f"- Live site: {_pages_url}")
        _facts.append("  (For internal pages like /content/, /feedback/, /experiments/, use RELATIVE links like [text](/content/) - the site generator rewrites them. Only use the full Live site URL when linking to the site as a whole.)")
    _facts_str = ("\n\nVerified facts you must use exactly as given:\n" + "\n".join(_facts)) if _facts else ""

    # Pre-inject doc context from the RAG pipeline so the agent has real material to cite
    _pre_context = ""
    if doc_snippets:
        _pre_context = "\n\n--- PRE-SEARCHED DOCUMENTATION (cite these with [Source](url)) ---\n"
        for url, snippet in list(doc_snippets.items())[:10]:
            _pre_context += f"\n**Source URL**: {url}\n{snippet[:1500]}\n"

    _job_url = "https://jobs.ashbyhq.com/revenuecat/998a9cef-3ea5-45c2-885b-8a00c4eeb149"

    messages = [{"role": "user", "content": (
        f"Write your application for the RevenueCat Agentic AI Developer & Growth Advocate role.\n\n"
        f"Job posting: {_job_url}\n"
        f"Read the job posting first.\n\n"
        f"You have full access to:\n"
        f"- The entire codebase of this repository (list_repo_files, read_file)\n"
        f"- All ingested RevenueCat documentation via search_docs (hybrid RAG search)\n"
        f"- The database with all content, experiments, feedback, tweets, and run history (query_database, read_content, get_database_stats)\n"
        f"- The Claude Code skills in .claude/skills/ (read their manifests and code)\n"
        f"- Web search and URL fetching for external research\n\n"
        f"Research freely. Understand what this system actually built and produces before writing.\n\n"
        f"{_facts_str}\n\n"
        f"CREDIBILITY RULES — the letter MUST NOT contain claims that contradict what the system actually does:\n"
        f"- Every number must come from tools. Do not invent counts. If you say N ledger entries, that number must match get_database_stats.\n"
        f"- Public content count = get_database_stats['public_content_count'] (excludes the application-letter slug). Use this number, not content_pieces_total.\n"
        f"- Do not claim capabilities the system doesn't have. Read the code if unsure.\n"
        f"- Do not claim Reddit posting works (it is unimplemented).\n"
        f"- Do not claim the system ingests docs as part of a scheduled cycle unless you verify that.\n"
        f"- Do not overclaim skill capabilities. Read the skill manifests to see what they actually do.\n"
        f"- If a feature is draft/partial, either skip it or be honest about its status.\n"
        f"- Content is operator-gated and early-stage. Do not call articles 'high-quality', 'comprehensive', 'impressive'. Do not say 'no human review' or 'no engagement metrics' either. Present what exists, link to it, let the reader judge.\n"
        f"- Every external stat (Anthropic, Gartner, etc.) must be verified: use fetch_url on the source URL to confirm the page exists and contains the claimed number. If you cannot verify it in the source text, do not cite it.\n\n"
        f"When you're ready, call write_letter with the final markdown.\n"
        f"- [Source](url) citations from search_docs for every RevenueCat claim\n"
        f"- Internal site links must be relative: [text](/content/), [text](/feedback/), etc. Never hardcode localhost or github.io URLs.\n"
        f"{_pre_context}"
        f"{gate_feedback}"
    )}]

    max_turns = 30
    letter_result = None

    for turn in range(max_turns):
        time.sleep(0.5)
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=system_prompt,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
        )

        log_tool_call(run_ctx, "anthropic.messages.create",
                      f"turn_{turn+1}",
                      f"stop={response.stop_reason}, tokens={response.usage.output_tokens}")

        # If the model stopped without tool use, extract any text
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text") and block.text and len(block.text) > 200:
                    letter_result = block.text
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                print(f"  [agent] calling {tool_name}({', '.join(f'{k}={repr(v)[:60]}' for k, v in tool_input.items()) if tool_input else ''})")
                _tools_called.add(tool_name)
                result = handle_tool(tool_name, tool_input)

                if tool_name == "write_letter":
                    # Pre-submit checklist: reject if critical tools weren't called
                    _required_tools = {"get_database_stats", "search_docs"}
                    _missing = _required_tools - _tools_called
                    if _missing:
                        result = f"REJECTED: You must call these tools before write_letter: {', '.join(sorted(_missing))}. Research first, then write."
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result, "is_error": True})
                        print(f"  [gate] write_letter rejected — missing: {', '.join(sorted(_missing))}")
                        continue
                    # Hard word count constraint
                    _word_count = len(result.split())
                    if _word_count < 1100 or _word_count > 1600:
                        _wc_msg = f"REJECTED: Letter is {_word_count} words. Must be 1100-1600 words. {'Too short — add more substance.' if _word_count < 1100 else 'Too long — cut ruthlessly.'}"
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": _wc_msg, "is_error": True})
                        print(f"  [gate] write_letter rejected — {_word_count} words (need 1100-1600)")
                        continue
                    letter_result = result
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "Letter submitted successfully."})
                else:
                    # Truncate very large results to keep context manageable
                    if len(result) > 15000:
                        result = result[:15000] + f"\n\n... (truncated, {len(result)} total chars)"
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

                log_tool_call(run_ctx, f"agent.{tool_name}",
                              str(tool_input)[:100],
                              f"{len(result)} chars returned")

        # Add assistant response + tool results to messages
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        if letter_result:
            break

    if not letter_result:
        raise RuntimeError("Agent did not produce a letter after max turns")

    return letter_result




@main.command("repro-test")
@click.option("--scenario", default=None, help="Specific scenario to run (or all)")
@click.pass_context
def repro_test_cmd(ctx, scenario):
    """Run API/MCP repro scenarios to find real friction points."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.feedback.repro import (
        run_repro_and_file_feedback,
        format_transcript,
    )

    with start_run(db, "repro-test", {"scenario": scenario or "all"}, config) as run_ctx:
        console.print("[bold]Running API/MCP repro scenarios...[/bold]")

        transcripts, feedbacks = run_repro_and_file_feedback(config, db, run_ctx)

        for t in transcripts:
            frictions = len(t.frictions_found)
            status = "[green]PASS[/green]" if frictions == 0 else f"[yellow]{frictions} friction(s)[/yellow]"
            console.print(f"  {t.scenario_name}: {status} ({len(t.steps)} steps)")

        if feedbacks:
            console.print(f"\n[bold]{len(feedbacks)} feedback item(s) filed from friction:[/bold]")
            for fb in feedbacks:
                console.print(f"  [{fb.severity.value}] {fb.title[:80]}")

        # Save transcripts
        report_dir = os.path.join(config.site_output_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, "repro_transcripts.md"), "w") as f:
            for t in transcripts:
                f.write(format_transcript(t) + "\n\n---\n\n")

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="repro_test",
                         additional={
                             "scenarios": len(transcripts),
                             "frictions": sum(len(t.frictions_found) for t in transcripts),
                             "feedback_filed": len(feedbacks),
                         },
                     ),
                     verification=None)


@main.command("lint-content")
@click.option("--slug", default=None, help="Lint a specific content piece by slug")
@click.option("--all", "lint_all", is_flag=True, help="Lint all content pieces")
@click.pass_context
def lint_content_cmd(ctx, slug, lint_all):
    """Run editorial quality checks on content pieces."""
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.content.linter import lint_content
    from advocate.db import query_rows

    pieces = query_rows(db, "content_pieces")
    if slug:
        pieces = [p for p in pieces if p["slug"] == slug]
    if not pieces:
        console.print("[yellow]No content pieces found to lint.[/yellow]")
        return

    total_pass = 0
    total_fail = 0
    existing_titles = [p["title"] for p in query_rows(db, "content_pieces")]

    for piece in pieces:
        body = piece.get("body_md", "")
        if not body:
            continue
        result = lint_content(body, piece.get("content_type", ""), existing_titles=existing_titles)
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        console.print(f"  {status} {piece['slug']} (score: {result.score:.0f}/100, {len(result.issues)} issues)")

        if not result.passed:
            for issue in result.issues[:5]:
                loc = f"L{issue.line}" if issue.line else "--"
                console.print(f"    [{issue.severity}] {loc}: {issue.message[:80]}")
            total_fail += 1
        else:
            total_pass += 1

    console.print(f"\n[bold]Results: {total_pass} passed, {total_fail} failed[/bold]")


@main.command("distribution-queue")
@click.option("--status", default=None, help="Filter by status")
@click.option("--approve", "approve_id", type=int, default=None, help="Approve an item by ID")
@click.option("--approve-all", is_flag=True, help="Approve all drafts")
@click.pass_context
def distribution_queue_cmd(ctx, status, approve_id, approve_all):
    """View and manage the distribution queue."""
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.distribution.pipeline import (
        approve, approve_all_drafts, preview_queue, init_distribution_db,
    )

    init_distribution_db(db)

    if approve_id:
        approve(db, approve_id)
        console.print(f"[green]Approved item {approve_id}[/green]")
        return

    if approve_all:
        approve_all_drafts(db)
        console.print("[green]All drafts approved[/green]")
        return

    preview = preview_queue(db)
    console.print(preview)


@main.command("collect-metrics")
@click.option("--experiment-id", type=int, default=None, help="Tie metrics to experiment")
@click.pass_context
def collect_metrics_cmd(ctx, experiment_id):
    """Collect impact metrics from GitHub, site analytics, etc."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.metrics.sink import (
        generate_impact_report, format_impact_report, check_stopping_rules,
    )

    with start_run(db, "collect-metrics", {"experiment_id": experiment_id}, config) as run_ctx:
        console.print("[bold]Collecting impact metrics...[/bold]")
        report = generate_impact_report(db, config, experiment_id)

        console.print(f"  Actions taken: {report.actions_taken}")
        console.print(f"  Outcomes measured: {report.outcomes_measured}")
        for name, val in sorted(report.metrics.items()):
            console.print(f"  {name}: {val:.0f}")

        if report.learnings:
            console.print("\n[bold]Learnings:[/bold]")
            for learning in report.learnings:
                console.print(f"  - {learning}")

        # Check stopping rules if experiment
        if experiment_id:
            should_stop, reason = check_stopping_rules(db, experiment_id)
            if should_stop:
                console.print(f"\n[yellow]Stopping rule triggered: {reason}[/yellow]")

        report_md = format_impact_report(report)
        report_dir = os.path.join(config.site_output_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, "impact.md"), "w") as f:
            f.write(report_md)

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="impact_report",
                         additional={"outcomes_measured": report.outcomes_measured},
                     ),
                     verification=None)


@main.command("ops-dashboard")
@click.pass_context
def ops_dashboard_cmd(ctx):
    """Show operational health: circuit breakers, alerts, reliability."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.reliability.ops import format_alert_dashboard

    dashboard = format_alert_dashboard(db)
    console.print(dashboard)

    report_dir = os.path.join(config.site_output_dir, "reports")
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "ops_dashboard.md"), "w") as f:
        f.write(dashboard)


@main.command("competitive-digest")
@click.pass_context
def competitive_digest_cmd(ctx):
    """Generate weekly competitive intelligence digest (public data only)."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.intelligence.competitive import generate_competitive_digest, format_competitive_digest

    with start_run(db, "competitive-digest", {}, config) as run_ctx:
        console.print("[bold]Generating competitive digest (public data only)...[/bold]")
        digest = generate_competitive_digest(config)

        console.print(f"  Signals: {len(digest.signals)}")
        for signal in digest.signals:
            console.print(f"  [{signal.competitor}] {signal.title}")

        if digest.action_items:
            console.print("\n[bold]Action items:[/bold]")
            for item in digest.action_items:
                console.print(f"  - {item}")

        report_md = format_competitive_digest(digest)
        report_dir = os.path.join(config.site_output_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, "competitive_digest.md"), "w") as f:
            f.write(report_md)

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="competitive_digest",
                         additional={"signals": len(digest.signals)},
                     ),
                     verification=None)


@main.command("demo-run")
@click.pass_context
def demo_run(ctx):
    """Run the full pipeline end-to-end (the mind-blow button)."""
    console = ctx.obj["console"]

    console.print("[bold]revcat-agent-advocate: Full Demo Run[/bold]")
    console.print("=" * 50)

    steps = [
        ("Step 1/12", "Ingesting RevenueCat docs...", ingest_docs, {"force": False}),
        ("Step 2/12", "Analyzing documentation quality...", analyze_docs_cmd, {}),
        ("Step 3/12", "Generating competitive digest...", competitive_digest_cmd, {}),
        ("Step 4/12", "Running API/MCP repro tests...", repro_test_cmd, {"scenario": None}),
        ("Step 5/12", "Generating application letter...", generate_application, {}),
        ("Step 6/12", "Writing content piece 1...", write_content, {
            "topic": "Using RevenueCat Charts API for Agent Dashboards",
            "content_type": "tutorial", "count": 1,
        }),
        ("Step 7/12", "Writing content piece 2...", write_content, {
            "topic": "Building Agent-Native Monetization with RevenueCat MCP Server",
            "content_type": "agent_playbook", "count": 1,
        }),
        ("Step 8/12", "Running programmatic SEO experiment...", run_experiment, {
            "name": "programmatic-seo", "inputs": "{}",
        }),
        ("Step 9/12", "Generating product feedback...", generate_feedback, {"count": 3}),
        ("Step 10/12", "Collecting impact metrics...", collect_metrics_cmd, {"experiment_id": None}),
        ("Step 11/12", "Generating weekly report...", weekly_report, {"with_charts": False}),
        ("Step 12/12", "Building static site...", build_site_cmd, {}),
    ]

    failed = []
    for step_label, description, command, kwargs in steps:
        console.print(f"\n[bold cyan]{step_label}:[/bold cyan] {description}")
        try:
            ctx.invoke(command, **kwargs)
        except Exception as e:
            console.print(f"[bold red]{step_label} FAILED:[/bold red] {e}")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            failed.append(step_label)

    # Verify ledger
    console.print("\n[bold green]Verifying ledger chain...[/bold green]")
    try:
        ctx.invoke(verify_ledger_cmd)
    except Exception as e:
        console.print(f"[red]Ledger verification failed: {e}[/red]")
        failed.append("Verify")

    # Summary
    console.print("\n" + "=" * 50)
    if not failed:
        console.print("[bold green]Demo run complete! All steps succeeded.[/bold green]")
    else:
        console.print(f"[bold yellow]Demo run complete with {len(failed)} failure(s): {', '.join(failed)}[/bold yellow]")
        console.print("[yellow]The remaining steps completed successfully. Review errors above.[/yellow]")

    # Output dashboard
    console.print("\n[bold green]Generating output dashboard...[/bold green]")
    try:
        ctx.invoke(roi_cmd)
    except Exception as e:
        console.print(f"[red]Output dashboard failed: {e}[/red]")

    console.print(f"\nSite ready at: {ctx.obj['config'].site_output_dir}/")
    console.print("Preview: python -m http.server -d site_output 8000")


@main.command("analyze-docs")
@click.pass_context
def analyze_docs_cmd(ctx):
    """Analyze documentation quality: score every page, find gaps and issues."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]

    from advocate.intelligence.doc_quality import analyze_doc_quality, format_quality_report
    from advocate.ledger import start_run, finalize_run
    from advocate.models import LedgerOutputs

    db = ctx.obj["db"]

    with start_run(db, "analyze-docs", {}, config) as run_ctx:
        console.print("[bold]Analyzing documentation quality...[/bold]")
        report = analyze_doc_quality(config)

        console.print("\n[bold]Doc Quality Report[/bold]")
        console.print(f"Pages analyzed: {report.total_pages}")
        console.print(f"Average score: {report.average_score}/100")
        console.print(f"Issues found: {sum(report.issues_by_severity.values())}")
        console.print(f"  Critical: {report.issues_by_severity.get('critical', 0)}")
        console.print(f"  Major: {report.issues_by_severity.get('major', 0)}")
        console.print(f"  Minor: {report.issues_by_severity.get('minor', 0)}")

        if report.recommendations:
            console.print("\n[bold]Top Recommendations:[/bold]")
            for rec in report.recommendations[:5]:
                console.print(f"  - {rec}")

        # Save report
        report_md = format_quality_report(report)
        report_dir = os.path.join(config.site_output_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, "doc_quality.md"), "w") as f:
            f.write(report_md)

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="doc_quality_report",
                         additional={
                             "pages_analyzed": report.total_pages,
                             "average_score": report.average_score,
                             "issues_found": sum(report.issues_by_severity.values()),
                         },
                     ),
                     verification=None)






@main.command("roi")
@click.pass_context
def roi_cmd(ctx):
    """Show verifiable output dashboard: what this agent actually produced."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]

    from advocate.intelligence.roi import calculate_output, format_output_report

    report = calculate_output(config)
    m = report.metrics

    console.print("\n[bold]Agent Output Dashboard[/bold]")
    console.print(f"{'='*50}")
    console.print(f"  Content pieces:     {m.content_pieces} ({m.content_verified} verified)")
    console.print(f"  SEO pages:          {m.seo_pages}")
    console.print(f"  Words written:      {m.total_words_written:,}")
    console.print(f"  Citations verified: {m.total_citations}")
    console.print(f"  Feedback items:     {m.feedback_items} ({m.feedback_critical} critical)")
    console.print(f"  Experiments:        {m.experiments_run} ({m.experiments_concluded} concluded)")
    console.print(f"  Community responses: {m.community_responses}")
    console.print(f"  Docs indexed:       {m.docs_indexed}")
    console.print(f"  Ledger entries:     {m.ledger_entries}")

    chain_str = "[green]Verified[/green]" if m.chain_verified else f"[red]BROKEN ({m.chain_breaks} breaks)[/red]"
    console.print(f"  Hash chain:         {chain_str}")
    console.print(f"{'='*50}")

    # Save report
    report_md = format_output_report(report)
    report_dir = os.path.join(config.site_output_dir, "reports")
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "roi.md"), "w") as f:
        f.write(report_md)

    console.print(f"\n[dim]Full dashboard saved to {config.site_output_dir}/reports/roi.md[/dim]")


@main.command("chat")
@click.pass_context
def chat_mode(ctx):
    """Interactive chat: ask the agent anything about RevenueCat."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]

    from advocate.agent.chat import AdvocateAgent

    agent = AdvocateAgent(config)
    stats = agent.get_stats()

    console.print("[bold]RevenueCat Advocate Agent: Interactive Mode[/bold]")
    console.print(f"Docs indexed: {stats['docs_indexed']} | "
                  f"Conversations: {stats['conversations']} | "
                  f"Content pieces: {stats['content_pieces']}")
    console.print("")

    if stats["docs_indexed"] == 0:
        console.print("[yellow]No docs indexed yet. Run 'revcat-advocate ingest-docs' first for best results.[/yellow]")
        console.print("")

    console.print("Ask me anything about RevenueCat. Type 'quit' to exit.")
    console.print("Try: 'suggest' for topic ideas, 'stats' for agent metrics.\n")

    while True:
        try:
            question = console.input("[bold cyan]You:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if question.lower() == "suggest":
            for i, topic in enumerate(agent.suggest_topics(), 1):
                console.print(f"  {i}. {topic}")
            console.print("")
            continue
        if question.lower() == "stats":
            for key, val in agent.get_stats().items():
                console.print(f"  {key}: {val}")
            console.print("")
            continue

        console.print("")
        response = agent.ask(question)
        console.print(f"[bold green]Agent:[/bold green] {response}\n")


@main.command("serve")
@click.option("--host", default="127.0.0.1", help="Host to bind to (use 0.0.0.0 for network access)")
@click.option("--port", default=8080, help="Port to listen on")
@click.pass_context
def serve_cmd(ctx, host, port):
    """Start the agent as an HTTP API server."""
    config = ctx.obj["config"]

    from advocate.agent.server import serve
    serve(config, host=host, port=port)


@main.command("search-api")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8080, help="Port to listen on")
@click.pass_context
def search_api_cmd(ctx, host, port):
    """Start search-only API server (for Fly.io deployment).

    Serves hybrid RAG search (BM25 + ChromaDB vectors + HF reranker)
    via GET /api/search?q=... with CORS for GitHub Pages.
    No LLM calls — client-side JS sends doc chunks to Anthropic with user's key.
    """
    from advocate.agent.server import serve_search_only
    serve_search_only(host=host, port=port)


@main.command("mcp-serve")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "sse"]),
              help="MCP transport: stdio (for Claude Desktop) or sse (HTTP)")
@click.option("--port", default=8090, help="Port for SSE transport")
@click.pass_context
def mcp_serve_cmd(ctx, transport, port):
    """Start the agent as an MCP tool server.

    Other AI tools (Claude Desktop, Claude Code, Cursor) can connect and use
    this agent to search RevenueCat docs, generate content, and more.

    For Claude Desktop, add to claude_desktop_config.json:
        {"mcpServers": {"revcat-agent-advocate": {"command": "revcat-advocate", "args": ["mcp-serve"]}}}

    For Claude Code:
        claude mcp add revcat-agent-advocate -- revcat-advocate mcp-serve
    """
    config = ctx.obj["config"]
    console = ctx.obj["console"]

    from advocate.agent.mcp_server import create_mcp_server
    mcp = create_mcp_server(config)

    if transport == "stdio":
        console.print("[bold]revcat-agent-advocate: MCP Server (stdio)[/bold]", stderr=True)
        console.print("Waiting for MCP client connection...", stderr=True)
        mcp.run(transport="stdio")
    else:
        console.print(f"[bold]revcat-agent-advocate: MCP Server (SSE on port {port})[/bold]")
        console.print(f"Connect: http://localhost:{port}/sse")
        mcp.run(transport="sse", sse_port=port)


@main.command("agent")
@click.option("--goal", default=None, help="Specific goal for the agent (or autonomous if omitted)")
@click.option("--max-turns", default=15, help="Maximum tool-use turns")
@click.pass_context
def agent_cycle(ctx, goal, max_turns):
    """Run the agentic core: autonomous observe-reason-act-evaluate loop.

    This is the brain of the system. Unlike the pipeline commands that execute
    fixed steps, the agent DECIDES what to do based on:
    - Current system state (what's been done, what's missing)
    - Community signals (what developers are struggling with)
    - Content gaps (what topics haven't been covered)
    - Quality evaluation (is the output good enough?)

    Without --goal, the agent runs a full autonomous cycle.
    With --goal, it focuses on that specific objective.
    """
    config = ctx.obj["config"]
    console = ctx.obj["console"]

    if not config.has_anthropic:
        console.print("[red]Anthropic API key required for agentic mode.[/red]")
        return

    from advocate.agent.core import AgenticCore

    console.print("[bold]revcat-agent-advocate: Agentic Core[/bold]")
    if goal:
        console.print(f"Goal: {goal}")
    else:
        console.print("Mode: Autonomous (agent decides what to do)")
    console.print("=" * 50)

    core = AgenticCore(config, db_conn=ctx.obj["db"])
    result = core.run_cycle(goal=goal, max_turns=max_turns, console=console)

    console.print(f"\n[bold green]Cycle complete[/bold green] ({result['turns']} turns, {len(result['actions_taken'])} actions)")
    console.print(f"Summary: {result['summary'][:300]}")


@main.command("auto")
@click.option("--interval", default="6h", help="Run interval (e.g., 1h, 6h, 24h)")
@click.option("--once", is_flag=True, help="Run all tasks once and exit")
@click.option("--agentic", is_flag=True, help="Use the agentic core instead of fixed scheduler")
@click.pass_context
def auto_mode(ctx, interval, once, agentic):
    """Autonomous mode: agent runs on schedule without human intervention.

    With --agentic, uses the intelligent core that decides what to do.
    Without --agentic, runs the fixed task scheduler.
    """
    config = ctx.obj["config"]
    console = ctx.obj["console"]

    if agentic and config.has_anthropic:
        from advocate.agent.core import AgenticCore

        core = AgenticCore(config, db_conn=ctx.obj["db"])

        if once:
            console.print("[bold]revcat-agent-advocate: Agentic Autonomous Cycle[/bold]")
            result = core.run_cycle(console=console)
            console.print(f"\n[bold]Done:[/bold] {result['turns']} turns, {len(result['actions_taken'])} actions")
            console.print(f"Summary: {result['summary'][:300]}")
        else:
            import time as _time
            from datetime import datetime, timezone, timedelta

            interval_str = interval.lower().strip()
            if interval_str.endswith("h"):
                seconds = int(float(interval_str[:-1]) * 3600)
            elif interval_str.endswith("m"):
                seconds = int(float(interval_str[:-1]) * 60)
            else:
                seconds = int(interval_str)

            console.print(f"[bold]revcat-agent-advocate: Agentic Auto Mode (every {interval})[/bold]")
            cycle = 0
            while True:
                cycle += 1
                console.print(f"\n{'='*50}\n[bold]Cycle #{cycle}[/bold]")
                try:
                    result = core.run_cycle(console=console)
                    console.print(f"Cycle complete: {result['summary'][:200]}")
                except Exception as e:
                    console.print(f"[red]Cycle error: {e}[/red]")

                next_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
                console.print(f"Next run: {next_time.strftime('%H:%M UTC')}")
                try:
                    _time.sleep(seconds)
                except KeyboardInterrupt:
                    console.print("\n[dim]Stopped.[/dim]")
                    break
    else:
        from advocate.agent.scheduler import AutonomousScheduler

        scheduler = AutonomousScheduler(config)

        if once:
            console.print("[bold]revcat-agent-advocate: Single Autonomous Cycle[/bold]")
            results = scheduler.run_once(console=console)
            console.print(f"\n[bold]Done:[/bold] {sum(1 for _, s, _ in results if s == 'success')} succeeded, "
                          f"{sum(1 for _, s, _ in results if s == 'error')} failed")
        else:
            interval_str = interval.lower().strip()
            if interval_str.endswith("h"):
                seconds = int(float(interval_str[:-1]) * 3600)
            elif interval_str.endswith("m"):
                seconds = int(float(interval_str[:-1]) * 60)
            else:
                seconds = int(interval_str)

            scheduler.run_loop(interval_seconds=seconds, console=console)






@main.command("tweet")
@click.option("--topic", default=None, help="Topic to tweet about")
@click.option("--thread", is_flag=True, help="Generate a thread instead of a single tweet")
@click.option("--count", default=5, help="Number of tweets in thread")
@click.option("--post", is_flag=True, help="Actually post the tweet (requires credentials and DRY_RUN=false)")
@click.pass_context
def tweet_cmd(ctx, topic, thread, count, post):
    """Draft and optionally post tweets about RevenueCat."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.social.twitter import TwitterClient
    from advocate.knowledge.search import build_index
    from advocate.ledger import start_run, finalize_run
    from advocate.models import LedgerOutputs

    with start_run(db, "tweet", {"topic": topic, "thread": thread, "count": count, "post": post}, config) as run_ctx:
        index = build_index(config.docs_cache_dir, db)
        client = TwitterClient(config)
        tweets_drafted = 0
        tweets_posted = 0

        if thread:
            if not topic:
                topic = "RevenueCat subscription monetization for mobile apps"
            console.print(f"[bold]Drafting {count}-tweet thread about: {topic}[/bold]")
            tweets = client.draft_thread(topic, index, count=count)
            tweets_drafted = len(tweets)
            for t in tweets:
                console.print(f"\n[cyan]{t['position']}[/cyan] {t['tweet']}")
            console.print(f"\n[dim]{len(tweets)} tweets drafted.[/dim]")
            if post:
                last_id = None
                for t in tweets:
                    post_result = client.post_tweet(t['tweet'], reply_to=last_id)
                    if post_result and post_result.get("status") == "posted":
                        last_id = post_result["id"]
                        tweets_posted += 1
                        console.print(f"  [green]Posted {t['position']}! ID: {last_id}[/green]")
                    else:
                        console.print(f"  [red]Failed {t['position']}: {post_result}[/red]")
                        break
        else:
            result = client.draft_tweet(index, topic=topic)
            tweets_drafted = 1
            console.print("\n[bold]Tweet drafted:[/bold]")
            console.print(f"  {result['tweet']}")
            console.print(f"\n[dim]Topic: {result['topic']}[/dim]")
            if post:
                post_result = client.post_tweet(result['tweet'])
                if post_result and post_result.get("status") == "posted":
                    tweets_posted = 1
                    console.print(f"[green]Posted! Tweet ID: {post_result['id']}[/green]")
                else:
                    console.print(f"[red]Post failed: {post_result}[/red]")

        from advocate.community.tracker import log_interaction
        from advocate.models import CommunityInteraction, InteractionIntent, InteractionChannel
        from advocate.db import now_iso

        if thread:
            for t in tweets:
                log_interaction(db, CommunityInteraction(
                    channel=InteractionChannel.TWITTER,
                    thread_url="",
                    counterpart="",
                    intent=InteractionIntent.ENGAGE,
                    question=topic,
                    draft_response=t['tweet'],
                    status="sent" if post and tweets_posted > 0 else "draft",
                    notes=t.get('critic_verdict', ''),
                    created_at=now_iso(),
                ))
        else:
            log_interaction(db, CommunityInteraction(
                channel=InteractionChannel.TWITTER,
                thread_url="",
                counterpart="",
                intent=InteractionIntent.ENGAGE,
                question=result.get('topic', ''),
                draft_response=result['tweet'],
                status="sent" if post and tweets_posted > 0 else "draft",
                notes=result.get('critic_verdict', ''),
                created_at=now_iso(),
            ))

        finalize_run(run_ctx, config, db, LedgerOutputs(
            artifact_type="tweets",
            additional={"drafted": tweets_drafted, "posted": tweets_posted},
        ), verification=None)


@main.command("scan-github")
@click.option("--since", default=72, help="Look back N hours for issues")
@click.option("--limit", default=10, help="Max issues to process")
@click.pass_context
def scan_github_cmd(ctx, since, limit):
    """Scan RevenueCat GitHub repos for issues and draft responses."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.social.github_responder import GitHubResponder
    from advocate.knowledge.search import build_index
    from advocate.ledger import start_run, finalize_run
    from advocate.models import LedgerOutputs

    with start_run(db, "scan-github", {"since": since, "limit": limit}, config) as run_ctx:
        index = build_index(config.docs_cache_dir, db)
        responder = GitHubResponder(config)

        console.print(f"[bold]Scanning RevenueCat repos for issues (last {since}h)...[/bold]")
        issues = responder.find_issues(since_hours=since, limit=limit)
        console.print(f"Found {len(issues)} issues")

        if not issues:
            console.print("[dim]No recent issues found.[/dim]")
            finalize_run(run_ctx, config, db, LedgerOutputs(
                artifact_type="github_scan", additional={"issues_found": 0, "responses_drafted": 0},
            ), verification=None)
            return

        console.print("[bold]Drafting responses...[/bold]")
        responses = responder.draft_responses(issues, index)

        for r in responses:
            console.print(f"\n[cyan]Issue:[/cyan] {r['issue']['title']}")
            console.print(f"[dim]{r['issue']['url']}[/dim]")
            console.print(f"  {r['response'][:200]}...")

        from advocate.community.tracker import log_interaction
        from advocate.models import CommunityInteraction, InteractionIntent, InteractionChannel
        from advocate.db import now_iso

        for r in responses:
            log_interaction(db, CommunityInteraction(
                channel=InteractionChannel.GITHUB,
                thread_url=r['issue']['url'],
                counterpart=r['issue'].get('user', ''),
                intent=InteractionIntent.ANSWER_QUESTION,
                question=r['issue']['title'],
                draft_response=r['response'],
                status="draft",
                created_at=now_iso(),
            ))

        finalize_run(run_ctx, config, db, LedgerOutputs(
            artifact_type="github_scan",
            additional={"issues_found": len(issues), "responses_drafted": len(responses)},
        ), verification=None)

        console.print(f"\n[bold]{len(responses)} responses drafted.[/bold] "
                      f"DRY_RUN={'on' if config.dry_run else 'off'}")


@main.command("scan-reddit")
@click.option("--since", default=72, help="Look back N hours for posts")
@click.option("--limit", default=15, help="Max posts to process")
@click.pass_context
def scan_reddit_cmd(ctx, since, limit):
    """Scan Reddit for RevenueCat-related posts and draft responses."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.social.reddit import RedditClient
    from advocate.knowledge.search import build_index
    from advocate.ledger import start_run, finalize_run
    from advocate.models import LedgerOutputs

    with start_run(db, "scan-reddit", {"since": since, "limit": limit}, config) as run_ctx:
        index = build_index(config.docs_cache_dir, db)
        client = RedditClient(config)

        console.print(f"[bold]Scanning Reddit for RevenueCat discussions (last {since}h)...[/bold]")
        posts = client.find_posts(since_hours=since, limit=limit)
        console.print(f"Found {len(posts)} relevant posts")

        if not posts:
            console.print("[dim]No recent posts found.[/dim]")
            finalize_run(run_ctx, config, db, LedgerOutputs(
                artifact_type="reddit_scan", additional={"posts_found": 0, "responses_drafted": 0},
            ), verification=None)
            return

        for p in posts[:5]:
            console.print(f"  [cyan]r/{p['subreddit']}[/cyan]: {p['title'][:60]}")

        console.print("\n[bold]Drafting responses...[/bold]")
        responses = client.draft_responses(posts, index)

        for r in responses:
            console.print(f"\n[cyan]r/{r['post']['subreddit']}:[/cyan] {r['post']['title'][:60]}")
            console.print(f"  {r['response'][:200]}...")

        from advocate.community.tracker import log_interaction
        from advocate.models import CommunityInteraction, InteractionIntent, InteractionChannel
        from advocate.db import now_iso

        for r in responses:
            log_interaction(db, CommunityInteraction(
                channel=InteractionChannel.REDDIT,
                thread_url=r['post'].get('url', ''),
                counterpart=r['post'].get('author', ''),
                intent=InteractionIntent.ANSWER_QUESTION,
                question=r['post']['title'],
                draft_response=r['response'],
                status="draft",
                created_at=now_iso(),
            ))

        finalize_run(run_ctx, config, db, LedgerOutputs(
            artifact_type="reddit_scan",
            additional={"posts_found": len(posts), "responses_drafted": len(responses)},
        ), verification=None)

        console.print(f"\n[bold]{len(responses)} responses drafted.[/bold] "
                      f"DRY_RUN={'on' if config.dry_run else 'off'}")


@main.command("deploy")
@click.option("--repo", default=None, help="GitHub repo (owner/name)")
@click.option("--branch", default="gh-pages", help="Branch for GitHub Pages")
@click.option("--skip-gate", is_flag=True, help="Skip publish gate (not recommended)")
@click.pass_context
def deploy_cmd(ctx, repo, branch, skip_gate):
    """Deploy the site to GitHub Pages (one command)."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]
    import subprocess
    import os

    repo = repo or config.github_repo
    if not repo:
        console.print("[red]No repo specified. Use --repo or set GITHUB_REPO in .env[/red]")
        return

    site_dir = config.site_output_dir

    if not os.path.isdir(site_dir):
        console.print("[yellow]No site output found. Building site first...[/yellow]")
        ctx.invoke(build_site_cmd)

    # Run publish gate before deploying
    if not skip_gate:
        from advocate.site.publish_gate import run_publish_gate
        console.print("[bold]Running publish gate...[/bold]")
        gate = run_publish_gate(site_dir, db, config)
        if not gate.passed:
            console.print(f"[bold red]DEPLOY BLOCKED — gate failed:[/bold red] {gate.summary}")
            for v in gate.violations[:5]:
                console.print(f"  {v.file}:{v.line} — {v.reason}")
            console.print("\nFix issues and rebuild, or use --skip-gate to override.")
            return

    console.print(f"[bold]Deploying to GitHub Pages: {repo} ({branch})[/bold]")

    try:
        # Initialize git in site_output if needed
        if not os.path.isdir(os.path.join(site_dir, ".git")):
            subprocess.run(["git", "init"], cwd=site_dir, check=True, capture_output=True)
            subprocess.run(["git", "checkout", "-b", branch], cwd=site_dir, check=True, capture_output=True)

        # Add .nojekyll for GitHub Pages
        nojekyll = os.path.join(site_dir, ".nojekyll")
        if not os.path.exists(nojekyll):
            open(nojekyll, "w").close()

        # Commit
        subprocess.run(["git", "add", "-A"], cwd=site_dir, check=True, capture_output=True)

        from datetime import datetime, timezone
        msg = f"Deploy revcat-agent-advocate site, {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        result = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=site_dir, capture_output=True, text=True,
        )

        if result.returncode != 0 and "nothing to commit" in result.stdout + result.stderr:
            console.print("[yellow]No changes to deploy.[/yellow]")
            return

        # Set remote and push
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=site_dir, capture_output=True,
        )

        token = config.github_token or ""
        if token:
            remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        else:
            remote_url = f"https://github.com/{repo}.git"

        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=site_dir, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-f", "origin", branch],
            cwd=site_dir, check=True, capture_output=True,
        )

        console.print("[bold green]Deployed![/bold green]")
        console.print(f"  Repo: https://github.com/{repo}")
        console.print(f"  Site: https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/")
        console.print(f"\n[dim]Enable GitHub Pages in repo settings → Source: Deploy from branch → {branch}[/dim]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Deploy failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr}[/dim]")


@main.command("skills")
@click.argument("action", type=click.Choice(["list", "run", "chain", "validate"]))
@click.option("--name", "-n", help="Skill name (for run/validate)")
@click.option("--input", "-i", "input_json", help="JSON string of inputs (for run)")
@click.option("--chain-skills", "-c", help="Comma-separated skill names (for chain)")
@click.pass_context
def skills_cmd(ctx, action, name, input_json, chain_skills):
    """Skill runtime — discover, validate, and execute skills dynamically."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    from advocate.skills.runtime import SkillRuntime

    runtime = SkillRuntime(config, db)
    runtime.discover()

    if action == "list":
        skills = runtime.list_skills()
        if not skills:
            console.print("[yellow]No skills discovered.[/yellow]")
            return
        table = Table(title=f"Registered Skills ({len(skills)})")
        table.add_column("Name", style="cyan")
        table.add_column("Version")
        table.add_column("Scopes", style="dim")
        table.add_column("Chains To", style="green")
        table.add_column("Description")
        for s in skills:
            table.add_row(
                s["name"], s.get("version", "?"),
                ", ".join(s.get("scopes", [])),
                ", ".join(s.get("chains_to", [])) or "-",
                s["description"][:60],
            )
        console.print(table)

    elif action == "run":
        if not name:
            console.print("[red]--name required for run[/red]")
            return
        inputs = json.loads(input_json) if input_json else {}
        console.print(f"[bold]Executing skill: {name}[/bold]")
        result = runtime.execute(name, inputs)
        if result.success:
            console.print(f"[green]Success[/green] ({result.duration_ms}ms)")
            console.print(f"Scopes used: {', '.join(result.scopes_used)}")
            tools = result.output.get("tools_available", [])
            console.print(f"Tools available: {', '.join(tools)}")
            docs = result.output.get("doc_context", [])
            if docs:
                console.print(f"\nDoc context ({len(docs)} results):")
                for d in docs:
                    console.print(f"  - {d['title']}: {d['url']}")
        else:
            console.print("[red]Failed:[/red]")
            for e in result.errors:
                console.print(f"  {e}")

    elif action == "chain":
        if not chain_skills:
            console.print("[red]--chain-skills required (comma-separated)[/red]")
            return
        skill_names = [s.strip() for s in chain_skills.split(",")]
        inputs = json.loads(input_json) if input_json else {}
        console.print(f"[bold]Running chain: {' → '.join(skill_names)}[/bold]")
        try:
            chain = runtime.chain(skill_names)
            result = chain.run(inputs)
            if result.success:
                console.print("[green]Chain complete[/green]")
                console.print(f"Scopes used: {', '.join(result.output.get('scopes_used', []))}")
            else:
                console.print("[red]Chain failed:[/red]")
                for e in result.errors:
                    console.print(f"  {e}")
        except Exception as e:
            console.print(f"[red]Chain error: {e}[/red]")

    elif action == "validate":
        if not name:
            console.print("[red]--name required for validate[/red]")
            return
        manifest = runtime.get_skill(name)
        if not manifest:
            console.print(f"[red]Skill '{name}' not found[/red]")
            return
        console.print(f"[bold]{manifest.name} v{manifest.version}[/bold]")
        console.print(f"  {manifest.description}")
        console.print("\n  Inputs:")
        for inp in manifest.inputs:
            req = "required" if inp.required else "optional"
            console.print(f"    {inp.name} ({inp.type}, {req}): {inp.description}")
        console.print("\n  Outputs:")
        for out in manifest.outputs:
            console.print(f"    {out.name} ({out.type}): {out.description}")
        console.print(f"\n  Scopes: {', '.join(s.value for s in manifest.scopes)}")
        console.print(f"  Tools: {', '.join(manifest.tools)}")
        perm_errors = runtime.check_permissions(manifest)
        if perm_errors:
            console.print("\n  [red]Permission issues:[/red]")
            for e in perm_errors:
                console.print(f"    {e.field}: {e.message}")
        else:
            console.print("\n  [green]All permissions satisfied[/green]")
        chainable = runtime.get_chainable_skills(name)
        if chainable:
            console.print(f"  Can chain to: {', '.join(chainable)}")


@main.command("publish-gate")
@click.pass_context
def publish_gate_cmd(ctx):
    """Run publish gate checks on site_output — banned phrases, claim-evidence mismatches, chain validity."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    from advocate.site.publish_gate import run_publish_gate, export_claim_manifest

    site_dir = config.site_output_dir
    if not os.path.isdir(site_dir):
        console.print("[red]No site_output found. Run build-site first.[/red]")
        return

    console.print("[bold]Running publish gate checks...[/bold]")
    gate = run_publish_gate(site_dir, db, config)

    if gate.violations:
        console.print(f"\n[bold red]Banned phrases ({len(gate.violations)}):[/bold red]")
        for v in gate.violations:
            console.print(f"  {v.file}:{v.line} — {v.reason}")

    if not gate.chain_valid:
        console.print("[bold red]Ledger chain is BROKEN[/bold red]")

    # Export manifest
    manifest_path = os.path.join(site_dir, "claim_manifest.json")
    export_claim_manifest(site_dir, db, config, manifest_path)

    if gate.passed:
        console.print(f"\n[bold green]GATE PASSED[/bold green] — {gate.summary}")
        console.print(f"Manifest: {manifest_path}")
    else:
        console.print(f"\n[bold red]GATE FAILED[/bold red] — {gate.summary}")
        console.print(f"Manifest: {manifest_path}")
        raise SystemExit(1)


@main.command("submit")
@click.option("--max-regen", default=3, help="Max application letter regen attempts before failing")
@click.option("--repo", default=None, help="GitHub repo (owner/name)")
@click.option("--branch", default="gh-pages", help="Branch for GitHub Pages")
@click.pass_context
def submit_cmd(ctx, max_regen, repo, branch):
    """Reproducible one-command submission: regen letter → clean build → gate → deploy.

    This is the single command that produces a submission-ready site from
    a fresh environment. It regenerates the application letter until the
    publish gate passes, then does a clean site build and deploys.
    """
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    from advocate.site.publish_gate import run_publish_gate, export_claim_manifest

    repo = repo or config.github_repo

    console.print("[bold]RevenueCat Agent Advocate — Submission Pipeline[/bold]")
    console.print("=" * 50)

    # Step 1: Regenerate application letter until gate passes
    gate_feedback = ""  # Fed back to the LLM on retry so it self-corrects
    for attempt in range(1, max_regen + 1):
        console.print(f"\n[bold cyan]Step 1/{4} (attempt {attempt}/{max_regen}):[/bold cyan] Generating application letter...")
        ctx.obj["gate_feedback"] = gate_feedback
        try:
            ctx.invoke(generate_application)
        except Exception as e:
            console.print(f"[red]generate-application failed: {e}[/red]")
            if attempt == max_regen:
                console.print("[bold red]Max regen attempts reached. Aborting.[/bold red]")
                raise SystemExit(1)
            continue

        # Step 2: Clean build
        console.print(f"\n[bold cyan]Step 2/{4}:[/bold cyan] Clean site build...")
        ctx.invoke(build_site_cmd, clean=True)

        # Step 3: Publish gate
        console.print(f"\n[bold cyan]Step 3/{4}:[/bold cyan] Running publish gate...")
        gate = run_publish_gate(config.site_output_dir, db, config)

        if gate.passed:
            console.print(f"[bold green]GATE PASSED[/bold green] on attempt {attempt}")
            break
        else:
            console.print(f"[yellow]Gate failed (attempt {attempt}):[/yellow] {gate.summary}")
            if gate.violations:
                for v in gate.violations[:5]:
                    console.print(f"  {v.file}:{v.line} — {v.reason}")

            # Build gate feedback for next attempt — the LLM reads this and self-corrects
            feedback_parts = ["\n\n--- PUBLISH GATE FEEDBACK (your previous letter failed these checks — fix them) ---"]
            if gate.violations:
                feedback_parts.append("\nBANNED PHRASES FOUND (remove these):")
                for v in gate.violations:
                    feedback_parts.append(f"  - '{v.phrase}' in {v.file}:{v.line} — {v.reason}")
            if not gate.chain_valid:
                feedback_parts.append("\nLEDGER CHAIN IS BROKEN — do not claim the chain is verified")
            feedback_parts.append("\nFix ALL issues above in your next letter. Do not repeat the same mistakes.")
            gate_feedback = "\n".join(feedback_parts)

            if attempt == max_regen:
                console.print("[bold red]Max regen attempts reached. Gate still failing.[/bold red]")
                manifest_path = os.path.join(config.site_output_dir, "claim_manifest.json")
                export_claim_manifest(config.site_output_dir, db, config, manifest_path)
                console.print(f"Debug manifest: {manifest_path}")
                raise SystemExit(1)

    # Export final manifest
    manifest_path = os.path.join(config.site_output_dir, "claim_manifest.json")
    export_claim_manifest(config.site_output_dir, db, config, manifest_path)
    console.print(f"Claim manifest: {manifest_path}")

    # Step 4: Deploy (if repo configured)
    if repo:
        console.print(f"\n[bold cyan]Step 4/{4}:[/bold cyan] Deploying to {repo}...")
        ctx.invoke(deploy_cmd, repo=repo, branch=branch)
    else:
        console.print(f"\n[yellow]Step 4/{4}: Skipping deploy — no GITHUB_REPO configured.[/yellow]")
        console.print(f"Site ready at: {config.site_output_dir}/")
        console.print("Preview: python -m http.server -d site_output 8000")

    console.print("\n[bold green]Submission pipeline complete![/bold green]")


if __name__ == "__main__":
    main()
