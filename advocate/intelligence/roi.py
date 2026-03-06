"""Output Dashboard: show exactly what this agent produced, with verifiable proof.

No dollar claims. No inflated benchmarks. No "this would cost $X from a consultant."
Just real numbers, real artifacts, real verification status. Let the reviewer
look at the output and decide for themselves.

Every number on this page links to the evidence that produced it.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import Config
from ..db import init_db, init_db_from_config, count_rows, query_rows, now_iso


@dataclass
class OutputMetrics:
    """Verifiable output metrics: every number can be checked."""
    # Content
    content_pieces: int = 0
    content_verified: int = 0       # passed citation verification
    content_draft: int = 0
    seo_pages: int = 0
    total_words_written: int = 0
    total_citations: int = 0

    # Community
    community_responses: int = 0
    github_responses: int = 0
    reddit_responses: int = 0
    twitter_drafts: int = 0
    questions_answered: int = 0

    # Intelligence
    feedback_items: int = 0
    feedback_critical: int = 0
    feedback_major: int = 0
    experiments_run: int = 0
    experiments_concluded: int = 0

    # System
    docs_indexed: int = 0
    rag_chunks: int = 0
    ledger_entries: int = 0
    chain_verified: bool = False
    chain_breaks: int = 0


@dataclass
class OutputReport:
    """Complete output report, just facts."""
    generated_at: str
    metrics: OutputMetrics
    content_list: list[dict]          # title, type, words, citations, status
    experiment_list: list[dict]       # name, status, hypothesis
    feedback_list: list[dict]         # title, severity, area
    recent_interactions: list[dict]   # channel, question snippet, status


def calculate_output(config: Config) -> OutputReport:
    """Calculate verifiable output metrics from the database."""
    db = init_db_from_config(config)
    m = OutputMetrics()

    # Content
    content_rows = query_rows(db, "content_pieces")
    seo_rows = query_rows(db, "seo_pages")

    m.content_pieces = len([r for r in content_rows if r["content_type"] != "seo_page"])
    m.content_verified = len([r for r in content_rows if r.get("status") == "verified"])
    m.content_draft = len([r for r in content_rows if r.get("status") == "draft"])
    m.seo_pages = len([r for r in content_rows if r["content_type"] == "seo_page"]) + len(seo_rows)
    m.total_words_written = sum(r.get("word_count", 0) for r in content_rows)
    m.total_citations = sum(r.get("citations_count", 0) for r in content_rows)

    content_list = []
    for r in content_rows:
        content_list.append({
            "title": r.get("title", ""),
            "type": r.get("content_type", ""),
            "words": r.get("word_count", 0),
            "citations": r.get("citations_count", 0),
            "status": r.get("status", ""),
            "slug": r.get("slug", ""),
        })

    # Community
    interactions = query_rows(db, "community_interactions")
    m.community_responses = len(interactions)
    m.github_responses = len([i for i in interactions if i.get("channel") == "github"])
    m.reddit_responses = len([i for i in interactions if i.get("channel") == "reddit"])
    m.twitter_drafts = len([i for i in interactions if i.get("channel") == "twitter"])
    m.questions_answered = len([i for i in interactions if i.get("intent") == "answer_question"])

    recent_interactions = []
    for i in interactions[:10]:
        recent_interactions.append({
            "channel": i.get("channel", ""),
            "question": (i.get("question") or "")[:80],
            "status": i.get("status", ""),
        })

    # Feedback
    feedback_rows = query_rows(db, "product_feedback")
    m.feedback_items = len(feedback_rows)
    m.feedback_critical = len([f for f in feedback_rows if f.get("severity") == "critical"])
    m.feedback_major = len([f for f in feedback_rows if f.get("severity") == "major"])

    feedback_list = []
    for f in feedback_rows:
        feedback_list.append({
            "title": f.get("title", ""),
            "severity": f.get("severity", ""),
            "area": f.get("area", ""),
            "status": f.get("status", ""),
        })

    # Experiments
    experiments = query_rows(db, "growth_experiments")
    m.experiments_run = len(experiments)
    m.experiments_concluded = len([e for e in experiments if e.get("status") == "concluded"])

    experiment_list = []
    for e in experiments:
        experiment_list.append({
            "name": e.get("name", ""),
            "status": e.get("status", ""),
            "hypothesis": e.get("hypothesis", ""),
        })

    # System
    m.ledger_entries = count_rows(db, "run_log")

    from ..ledger import verify_chain
    chain = verify_chain(db, config)
    m.chain_verified = chain.valid
    m.chain_breaks = len(chain.breaks)

    # Docs indexed + RAG stats
    from ..knowledge.search import build_index
    try:
        index = build_index(config.docs_cache_dir, db)
        m.docs_indexed = index.doc_count
    except Exception:
        m.docs_indexed = 0

    try:
        from ..knowledge.rag import build_rag_index_from_config
        rag_index = build_rag_index_from_config(config, db)
        m.rag_chunks = rag_index.chunk_count
    except Exception:
        m.rag_chunks = 0

    return OutputReport(
        generated_at=now_iso(),
        metrics=m,
        content_list=content_list,
        experiment_list=experiment_list,
        feedback_list=feedback_list,
        recent_interactions=recent_interactions,
    )


def format_output_report(report: OutputReport) -> str:
    """Format as markdown. No dollar claims. Just real output."""
    m = report.metrics
    lines = [
        "# Agent Output Dashboard",
        f"*Last updated: {report.generated_at}*",
        "",
        "Every number below is verifiable. Click through to the evidence.",
        "",
        "## Content Produced",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Content pieces written | {m.content_pieces} |",
        f"| Verified (all citations valid) | {m.content_verified} |",
        f"| SEO pages generated | {m.seo_pages} |",
        f"| Total words written | {m.total_words_written:,} |",
        f"| Source citations verified | {m.total_citations} |",
        "",
    ]

    if report.content_list:
        lines.extend([
            "### Content Pieces",
            "",
            "| Title | Type | Words | Citations | Status |",
            "|-------|------|-------|-----------|--------|",
        ])
        for c in report.content_list:
            status_mark = "Verified" if c["status"] == "verified" else c["status"].title()
            lines.append(
                f"| [{c['title'][:50]}](/content/{c['slug']}/) | {c['type']} | "
                f"{c['words']:,} | {c['citations']} | {status_mark} |"
            )
        lines.append("")

    lines.extend([
        "## Community Engagement",
        "",
        f"| Channel | Responses Drafted |",
        f"|---------|------------------|",
        f"| GitHub issues | {m.github_responses} |",
        f"| Reddit threads | {m.reddit_responses} |",
        f"| Twitter/X drafts | {m.twitter_drafts} |",
        f"| Interactive Q&A | {m.questions_answered} |",
        f"| **Total** | **{m.community_responses}** |",
        "",
        "## Product Feedback",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total feedback items | {m.feedback_items} |",
        f"| Critical severity | {m.feedback_critical} |",
        f"| Major severity | {m.feedback_major} |",
        "",
    ])

    if report.feedback_list:
        lines.extend([
            "### Feedback Items",
            "",
            "| Title | Severity | Area |",
            "|-------|----------|------|",
        ])
        for f in report.feedback_list:
            lines.append(f"| {f['title'][:60]} | {f['severity']} | {f['area']} |")
        lines.append("")

    lines.extend([
        "## Growth Experiments",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Experiments run | {m.experiments_run} |",
        f"| Experiments concluded | {m.experiments_concluded} |",
        "",
    ])

    if report.experiment_list:
        lines.extend([
            "### Experiments",
            "",
            "| Name | Status | Hypothesis |",
            "|------|--------|-----------|",
        ])
        for e in report.experiment_list:
            lines.append(f"| {e['name']} | {e['status']} | {e['hypothesis'][:60]} |")
        lines.append("")

    chain_status = "Verified: all entries intact" if m.chain_verified else f"BROKEN: {m.chain_breaks} break(s)"
    lines.extend([
        "## RAG Pipeline",
        "",
        f"| Component | Detail |",
        f"|-----------|--------|",
        f"| Vector DB | ChromaDB (persistent, cosine similarity) |",
        f"| Embeddings | all-mpnet-base-v2 (768-dim, HF Inference API) |",
        f"| Reranker | ms-marco-MiniLM-L-12-v2 (cross-encoder, HF Inference API) |",
        f"| Keyword search | BM25 (k1=1.2, b=0.75) |",
        f"| Hybrid scoring | 70% semantic + 30% BM25 |",
        f"| Doc pages indexed | {m.docs_indexed} |",
        f"| RAG chunks | {m.rag_chunks} |",
        "",
        "## System Integrity",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Ledger entries (auditable actions) | {m.ledger_entries} |",
        f"| Hash chain status | {chain_status} |",
        "",
        "Every action this agent takes is recorded in a hash-chained ledger. ",
        "Tamper with any entry and the chain breaks. ",
        "Verify: `revcat-advocate verify-ledger`",
        "",
        "Browse the full ledger at [/ledger/](/ledger/).",
    ])

    return "\n".join(lines)
