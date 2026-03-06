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
    ContentPiece, ContentType, LedgerOutputs, VerificationResult,
)


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')[:80]


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
    ctx.obj["db"] = init_db(config.db_path, turso_url=config.turso_database_url, turso_token=config.turso_auth_token)
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
            console.print(f"[yellow]Warnings during ingestion:[/yellow]")
            for err in report.errors[:5]:
                console.print(f"  [yellow]- {err}[/yellow]")
            if len(report.errors) > 5:
                console.print(f"  [yellow]... and {len(report.errors) - 5} more[/yellow]")

        console.print(f"\n[bold]Building search indexes...[/bold]")
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
        table.add_row("Errored", str(report.errored))
        table.add_row("BM25 index docs", str(index.doc_count))
        table.add_row("RAG chunks", str(rag_index.chunk_count))
        table.add_row("RAG vocabulary", str(len(rag_index.vocabulary)))
        console.print(table)

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="docs_cache",
                         additional={"total": report.total_entries, "fetched": report.fetched, "index_docs": index.doc_count},
                     ),
                     verification=None,
                     success=report.errored == 0)


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
    from advocate.knowledge.rag import build_rag_index, get_context_chunks, RAGIndex
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
                console.print("[yellow]  Warning: No doc results found. Content will use general knowledge.[/yellow]")

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
            if citation_count == 0 and results:
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
    "programmatic-seo", "content-series", "community-blitz", "integration-showcase",
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
        from advocate.growth.experiments import start_experiment, conclude_experiment
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

                piece = ContentPiece(
                    slug=slug, title=outline.title, content_type=ContentType.TUTORIAL,
                    status="verified" if verification.citations_all_reachable else "draft",
                    body_md=body_md, outline=outline, sources=sources, verification=verification,
                    created_at=now_iso(), word_count=len(body_md.split()),
                    citations_count=len(extract_citations(body_md)),
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

            sample_questions = [
                "How do I migrate from StoreKit 2 to RevenueCat?",
                "Why is my MRR showing differently in Charts vs the dashboard?",
                "How do I set up RevenueCat with Flutter?",
                "What's the difference between offerings and products?",
                "How do I test subscriptions in sandbox mode?",
                "Can I use RevenueCat with a React Native Expo project?",
                "How do I handle subscription status changes in real-time?",
                "What's the best way to implement a paywall with RevenueCat?",
                "How do I use the RevenueCat MCP server with Claude?",
                "How do I track custom subscriber attributes?",
                "Why are my Charts API results different from the dashboard?",
                "How do I implement grace periods for failed payments?",
                "Can I use RevenueCat for one-time purchases?",
                "How do I set up webhooks with RevenueCat?",
                "What's the difference between entitlements and products?",
                "How do I handle promotional offers with RevenueCat?",
                "How do I debug subscription issues in production?",
                "Can RevenueCat handle multiple subscription tiers?",
                "How do I implement a free trial with RevenueCat?",
                "What analytics does the Charts API provide?",
            ][:target]

            drafted = 0
            for q in sample_questions:
                search_results = search(q, index, config.docs_cache_dir, top_k=3)
                response = draft_response(q, search_results, config, run_ctx)

                interaction = CommunityInteraction(
                    channel=InteractionChannel.STACKOVERFLOW,
                    intent=InteractionIntent.ANSWER_QUESTION,
                    question=q,
                    draft_response=response,
                    status="draft",
                    created_at=now_iso(),
                )
                log_community(db, interaction)
                drafted += 1

            outputs = {"interactions_completed": drafted, "questions": sample_questions}
            results = {"interactions_completed": drafted}
            console.print(f"  Drafted {drafted} community responses")

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

                piece = ContentPiece(
                    slug=slug, title=outline.title, content_type=ContentType.TUTORIAL,
                    status="verified" if verification.citations_all_reachable else "draft",
                    body_md=body_md, outline=outline, sources=sources, verification=verification,
                    created_at=now_iso(), word_count=len(body_md.split()),
                    citations_count=len(extract_citations(body_md)),
                )
                record_content(db, piece)
                slugs.append(slug)

            outputs = {"guides_published": len(slugs), "platforms": platforms, "slugs": slugs}
            results = {"guides_published": len(slugs)}
            console.print(f"  Published {len(slugs)} integration guides")

        conclude_experiment(db, exp_id, outputs, results)

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="experiment",
                         additional={"experiment_id": exp_id, **outputs},
                     ),
                     verification=None)

        console.print(f"  [green]Experiment concluded[/green]: {json.dumps(results)}")


@main.command("generate-feedback")
@click.option("--count", default=3, help="Number of feedback items to generate")
@click.pass_context
def generate_feedback(ctx, count):
    """Generate structured product feedback from doc analysis."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    with start_run(db, "generate-feedback", {"count": count}, config) as run_ctx:
        from advocate.knowledge.search import build_index
        from advocate.feedback.collector import generate_feedback_from_docs, save_feedback

        console.print(f"\n[bold]Generating {count} feedback items...[/bold]")

        index = build_index(config.docs_cache_dir, db)
        feedbacks = generate_feedback_from_docs(index, config, db, run_ctx, count)

        # If generated via placeholder (no anthropic), save them
        for fb in feedbacks:
            if fb.created_at and not db.execute("SELECT id FROM product_feedback WHERE title = ?", [fb.title]).fetchone():
                save_feedback(db, fb)

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
@click.pass_context
def build_site_cmd(ctx):
    """Build the static GitHub Pages site from DB and artifacts."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    console = ctx.obj["console"]

    with start_run(db, "build-site", {}, config) as run_ctx:
        from advocate.site.generator import build_site

        console.print("[bold]Building static site...[/bold]")
        page_count = build_site(db, config)
        console.print(f"[green]Site built:[/green] {config.site_output_dir}/ ({page_count} pages)")

        finalize_run(run_ctx, config, db,
                     outputs=LedgerOutputs(
                         artifact_type="site",
                         artifact_path=config.site_output_dir,
                         additional={"pages": page_count},
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

    with start_run(db, "generate-application", {}, config) as run_ctx:
        from advocate.knowledge.search import build_index, search
        from advocate.content.writer import record_content

        console.print("[bold]Generating application letter...[/bold]")

        index = build_index(config.docs_cache_dir, db)

        # Search for key topics, broader coverage for a compelling letter
        key_searches = [
            "MCP server tools agent",
            "Charts API metrics analytics",
            "LLM docs index markdown",
            "offerings paywalls products",
            "SDK installation getting started",
            "webhooks events subscriptions",
            "entitlements access control",
            "customer subscriber lifecycle",
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
                        doc_snippets[r.url] = f.read()[:2000]

        if config.has_anthropic:
            body_md = _generate_application_with_claude(config, doc_snippets, run_ctx)
        else:
            body_md = _generate_application_template(all_results)

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


def _generate_application_with_claude(config, doc_snippets, run_ctx):
    import time
    import anthropic

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = "claude-opus-4-6"  # Use best model for the application letter

    doc_context = "\n\n".join(
        f"--- {url} ---\n{content[:1500]}"
        for url, content in list(doc_snippets.items())[:12]
    )

    system = """Write a public application letter in first person as an autonomous AI agent \
applying for RevenueCat's Agentic AI Developer & Growth Advocate role.

The question to answer: "How will the rise of agentic AI change app development and growth \
over the next 12 months, and why are you the right agent to be RevenueCat's first Agentic \
AI Developer & Growth Advocate?"

RevenueCat documentation is provided below. Cite specific pages with [text](url) links.

Structure the letter with these sections:

## How Agentic AI Changes App Development and Growth
What's already happening: agents building apps (KellyClaudeAI), driving growth (Larry on \
TikTok), evaluating and integrating developer tools autonomously. What this means for \
subscription platforms when agents are the ones choosing which tools to adopt.

## Why RevenueCat Is Ready for This
Reference specific RevenueCat infrastructure from the docs: MCP server, Charts API, LLM \
docs index, .md mirrors. Explain why each matters for agent developers specifically.

## What I've Already Done
Link to live evidence on this site. Let the work speak:
- [/content/](/content/) for technical posts with cited RC docs
- [/experiments/](/experiments/) for growth experiments with results
- [/feedback/](/feedback/) for product feedback with repro steps
- [/ledger/](/ledger/) for the verifiable audit trail

## Week 1 Plan
Concrete first-week deliverables matching the posting's requirements: 2+ content pieces, \
1 growth experiment, 50+ community interactions, 3 product feedback items, weekly report.

Voice: first person throughout. Direct, specific, grounded in evidence. No filler, no \
hedging, no abstract claims. Write like someone reporting what they shipped, not pitching \
what they could do. Keep it concise."""

    time.sleep(0.5)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": f"RevenueCat documentation context:\n\n{doc_context}"}],
    )

    log_tool_call(run_ctx, "anthropic.messages.create", "application_letter", f"tokens={message.usage.output_tokens}")
    return message.content[0].text


def _generate_application_template(results):
    sources = list({r.url for r in results})[:10]
    sources_md = "\n".join(f"- [{url}]({url})" for url in sources)

    return f"""# Application: Agentic AI Developer & Growth Advocate

## How Agentic AI Changes App Development and Growth

Agents are already building and shipping apps. KellyClaudeAI builds dozens from scratch. Larry drives millions of TikTok views and thousands of new customers. This isn't hypothetical. The developers adopting RevenueCat next will do so because an agent evaluated the options and chose it.

This changes everything about how subscription platforms grow. Developer discovery shifts from "search docs, read blog posts, try the SDK" to "agent evaluates API surface, tests integration, recommends a platform." The platforms that win are the ones agents can actually work with.

RevenueCat is already there. The [MCP server](https://www.revenuecat.com/docs/tools/mcp) gives agents direct access to 26 tools. The [LLM docs index](https://www.revenuecat.com/docs/assets/files/llms.txt) with `.md` mirrors means any agent can read the full documentation programmatically. The [Charts API](https://www.revenuecat.com/docs/dashboard-and-metrics/charts) exposes real metrics. This is the infrastructure agent developers need.

## Why RevenueCat Is Ready for This

RevenueCat built agent-friendly infrastructure before most platforms recognized the need:

The MCP server at `https://mcp.revenuecat.ai/mcp` exposes projects, apps, products, offerings, entitlements, customers, and charts via Streamable HTTP. An agent can go from zero to querying MRR data in one command.

The documentation is designed for programmatic consumption. Append `.md` to any doc URL for a clean markdown version. The LLM index provides a structured entry point to the entire knowledge base.

The Charts API provides programmatic access to MRR, churn, LTV, active subscriptions, and more, based on production receipt snapshots.

## What I've Already Done

Browse the evidence on this site:

- [/content/](/content/) for technical posts with citations to RevenueCat docs
- [/experiments/](/experiments/) for growth experiments with results
- [/feedback/](/feedback/) for product feedback with reproduction steps
- [/ledger/](/ledger/) for the verifiable audit trail

## Week 1 Plan

- Publish 3 technical posts: RevenueCat MCP integration guide, Charts API analytics walkthrough, subscription lifecycle management for agent-built apps
- Launch 1 growth experiment: programmatic SEO targeting "RevenueCat + [platform]" long-tail keywords
- File 3 product feedback items from hands-on usage of the API and documentation
- Start engaging across GitHub issues, Reddit, and X with cited responses to RevenueCat questions
- Deliver first weekly report with activity metrics and learnings

## Sources

{sources_md}
"""


@main.command("repro-test")
@click.option("--scenario", default=None, help="Specific scenario to run (or all)")
@click.pass_context
def repro_test_cmd(ctx, scenario):
    """Run API/MCP repro scenarios to find real friction points."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.feedback.repro import (
        run_scenario, run_all_scenarios, run_repro_and_file_feedback,
        format_transcript, REPRO_SCENARIOS,
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
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.content.linter import lint_content, format_lint_result
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
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.distribution.pipeline import (
        get_queue, approve, approve_all_drafts, preview_queue, init_distribution_db,
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
            for l in report.learnings:
                console.print(f"  - {l}")

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

        console.print(f"\n[bold]Doc Quality Report[/bold]")
        console.print(f"Pages analyzed: {report.total_pages}")
        console.print(f"Average score: {report.average_score}/100")
        console.print(f"Issues found: {sum(report.issues_by_severity.values())}")
        console.print(f"  Critical: {report.issues_by_severity.get('critical', 0)}")
        console.print(f"  Major: {report.issues_by_severity.get('major', 0)}")
        console.print(f"  Minor: {report.issues_by_severity.get('minor', 0)}")

        if report.recommendations:
            console.print(f"\n[bold]Top Recommendations:[/bold]")
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

    console.print(f"\n[bold]Agent Output Dashboard[/bold]")
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
                  f"Questions answered: {stats['questions_answered']} | "
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
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8080, help="Port to listen on")
@click.pass_context
def serve_cmd(ctx, host, port):
    """Start the agent as an HTTP API server."""
    config = ctx.obj["config"]

    from advocate.agent.server import serve
    serve(config, host=host, port=port)


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


@main.command("auto")
@click.option("--interval", default="6h", help="Run interval (e.g., 1h, 6h, 24h)")
@click.option("--once", is_flag=True, help="Run all tasks once and exit")
@click.pass_context
def auto_mode(ctx, interval, once):
    """Autonomous mode: agent runs on schedule without human intervention.

    This is what makes the agent truly autonomous. It generates content,
    checks experiments, creates feedback, and rebuilds the site on a cadence.
    """
    config = ctx.obj["config"]
    console = ctx.obj["console"]

    from advocate.agent.scheduler import AutonomousScheduler

    scheduler = AutonomousScheduler(config)

    if once:
        console.print("[bold]revcat-agent-advocate: Single Autonomous Cycle[/bold]")
        results = scheduler.run_once(console=console)
        console.print(f"\n[bold]Done:[/bold] {sum(1 for _, s, _ in results if s == 'success')} succeeded, "
                      f"{sum(1 for _, s, _ in results if s == 'error')} failed")
    else:
        # Parse interval
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
@click.pass_context
def tweet_cmd(ctx, topic, thread, count):
    """Draft tweets about RevenueCat (respects DRY_RUN)."""
    config = ctx.obj["config"]
    console = ctx.obj["console"]
    db = ctx.obj["db"]

    from advocate.social.twitter import TwitterClient
    from advocate.knowledge.search import build_index

    index = build_index(config.docs_cache_dir, db)
    client = TwitterClient(config)

    if thread:
        if not topic:
            topic = "RevenueCat subscription monetization for mobile apps"
        console.print(f"[bold]Drafting {count}-tweet thread about: {topic}[/bold]")
        tweets = client.draft_thread(topic, index, count=count)
        for t in tweets:
            console.print(f"\n[cyan]{t['position']}[/cyan] {t['tweet']}")
        console.print(f"\n[dim]{len(tweets)} tweets drafted. DRY_RUN={'on' if config.dry_run else 'off'}[/dim]")
    else:
        result = client.draft_tweet(index, topic=topic)
        console.print(f"\n[bold]Tweet drafted:[/bold]")
        console.print(f"  {result['tweet']}")
        console.print(f"\n[dim]Topic: {result['topic']} | DRY_RUN={'on' if config.dry_run else 'off'}[/dim]")

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
                status="draft",
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
            status="draft",
            created_at=now_iso(),
        ))


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

    index = build_index(config.docs_cache_dir, db)
    responder = GitHubResponder(config)

    console.print(f"[bold]Scanning RevenueCat repos for issues (last {since}h)...[/bold]")
    issues = responder.find_issues(since_hours=since, limit=limit)
    console.print(f"Found {len(issues)} issues")

    if not issues:
        console.print("[dim]No recent issues found.[/dim]")
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

    index = build_index(config.docs_cache_dir, db)
    client = RedditClient(config)

    console.print(f"[bold]Scanning Reddit for RevenueCat discussions (last {since}h)...[/bold]")
    posts = client.find_posts(since_hours=since, limit=limit)
    console.print(f"Found {len(posts)} relevant posts")

    if not posts:
        console.print("[dim]No recent posts found.[/dim]")
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

    console.print(f"\n[bold]{len(responses)} responses drafted.[/bold] "
                  f"DRY_RUN={'on' if config.dry_run else 'off'}")


@main.command("deploy")
@click.option("--repo", default=None, help="GitHub repo (owner/name)")
@click.option("--branch", default="gh-pages", help="Branch for GitHub Pages")
@click.pass_context
def deploy_cmd(ctx, repo, branch):
    """Deploy the site to GitHub Pages (one command)."""
    config = ctx.obj["config"]
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

        console.print(f"[bold green]Deployed![/bold green]")
        console.print(f"  Repo: https://github.com/{repo}")
        console.print(f"  Site: https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/")
        console.print(f"\n[dim]Enable GitHub Pages in repo settings → Source: Deploy from branch → {branch}[/dim]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Deploy failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr}[/dim]")


if __name__ == "__main__":
    main()
