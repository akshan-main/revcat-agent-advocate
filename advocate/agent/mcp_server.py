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
        return agent.ask(question)

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

        Creates an outline and draft article with citations from ingested docs.
        Does NOT run automated verification — content is saved as 'draft' status.
        content_type can be: tutorial, case_study, or agent_playbook.
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

        # Persist to database
        slug = re.sub(r'[^a-z0-9]+', '-', topic.lower()).strip('-')[:80]
        from ..db import insert_row, now_iso
        insert_row(db, "content_pieces", {
            "slug": slug,
            "title": outline.title,
            "content_type": content_type,
            "status": "draft",
            "body_md": body,
            "outline_json": outline.model_dump_json() if outline else None,
            "sources_json": "[]",
            "created_at": now_iso(),
            "word_count": word_count,
            "citations_count": citations,
        })

        return (
            f"✅ **Content Generated**\n\n"
            f"**Title:** {outline.title}\n"
            f"**Type:** {content_type}\n"
            f"**Words:** {word_count}\n"
            f"**Citations:** {citations}\n\n"
            f"---\n\n{body[:2000]}{'...' if len(body) > 2000 else ''}"
        )

    # ── System Knowledge Tools ─────────────────────────────────────────

    @mcp.tool()
    def read_source_file(file_path: str) -> str:
        """Read a source file from the agent's codebase.

        Returns the full content of any Python, HTML, CSS, TOML, or YAML file
        in the repository. Use list_source_files() first to see available files.

        Examples: "advocate/agent/mcp_server.py", "cli.py", "advocate/ledger.py"
        """
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_path = os.path.join(repo_root, file_path)
        # Security: only allow files within the repo (realpath prevents symlink/traversal bypass)
        if not os.path.realpath(full_path).startswith(os.path.realpath(repo_root) + os.sep):
            return "Access denied: path outside repository."
        # Firewall check
        from .firewall import check as fw_check
        verdict = fw_check("read_file", {"path": file_path})
        if not verdict:
            return f"Firewall denied: {verdict.reason}"
        # Block sensitive files
        basename = os.path.basename(file_path)
        BLOCKED = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}
        if basename in BLOCKED or ".env" in basename:
            return f"Access denied: {basename} is a sensitive file."
        # Only allow source file extensions
        ALLOWED_EXT = {".py", ".html", ".css", ".toml", ".yml", ".yaml", ".md", ".txt", ".json", ".cfg"}
        _, ext = os.path.splitext(full_path)
        if ext.lower() not in ALLOWED_EXT:
            return f"Access denied: {ext} files are not readable."
        if not os.path.exists(full_path):
            return f"File not found: {file_path}"
        try:
            with open(full_path, "r") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"

    @mcp.tool()
    def list_source_files() -> str:
        """List all source files in the agent's codebase.

        Returns a tree of Python, HTML, CSS, TOML, and YAML files with line counts.
        Use read_source_file() to read any specific file.
        """
        import os
        import glob as globmod
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        files = []
        for pattern in ["**/*.py", "**/*.html", "**/*.css", "**/*.toml", "**/*.yml", "**/*.md"]:
            for fpath in globmod.glob(os.path.join(repo_root, pattern), recursive=True):
                rel = os.path.relpath(fpath, repo_root)
                if any(skip in rel for skip in ["__pycache__", "site_output", ".docs_cache", ".egg", ".pytest_cache"]):
                    continue
                try:
                    with open(fpath, "r") as f:
                        lines = len(f.readlines())
                    files.append(f"  {rel} ({lines} lines)")
                except Exception:
                    files.append(f"  {rel}")
        return "**Agent Source Files**\n\n" + "\n".join(sorted(files))

    @mcp.tool()
    def get_content_body(slug: str) -> str:
        """Get the full markdown body of a content piece by slug.

        Returns the complete generated article including citations, code snippets,
        and sources section. Use list_content() to see available slugs.
        """
        from ..db import query_rows
        rows = query_rows(db, "content_pieces")
        for row in rows:
            if row.get("slug") == slug:
                return (
                    f"**{row['title']}**\n"
                    f"Type: {row['content_type']} | Words: {row['word_count']} | "
                    f"Citations: {row['citations_count']} | Status: {row['status']}\n\n"
                    f"---\n\n{row.get('body_md', 'No body available')}"
                )
        return f"No content piece found with slug '{slug}'."

    @mcp.tool()
    def get_experiment_details(name: str) -> str:
        """Get full details of a growth experiment by name.

        Returns hypothesis, metric, channel, tactic, inputs, outputs, results,
        and timeline. Use list_experiments() to see available experiments.
        """
        from ..db import query_rows
        import json
        rows = query_rows(db, "growth_experiments")
        for row in rows:
            if row.get("name") == name:
                outputs = row.get("outputs_json")
                results = row.get("results_json")
                if isinstance(outputs, str):
                    try:
                        outputs = json.loads(outputs)
                    except (json.JSONDecodeError, ValueError):
                        pass
                if isinstance(results, str):
                    try:
                        results = json.loads(results)
                    except (json.JSONDecodeError, ValueError):
                        pass
                return (
                    f"**Experiment: {row['name']}**\n\n"
                    f"- **Hypothesis:** {row['hypothesis']}\n"
                    f"- **Metric:** {row['metric']}\n"
                    f"- **Channel:** {row['channel']}\n"
                    f"- **Tactic:** {row['tactic']}\n"
                    f"- **Status:** {row['status']}\n"
                    f"- **Started:** {row.get('created_at', 'N/A')}\n"
                    f"- **Concluded:** {row.get('concluded_at', 'N/A')}\n\n"
                    f"**Outputs:**\n{json.dumps(outputs, indent=2) if outputs else 'N/A'}\n\n"
                    f"**Results:**\n{json.dumps(results, indent=2) if results else 'N/A'}"
                )
        return f"No experiment found with name '{name}'."

    @mcp.tool()
    def get_feedback_details(title: str) -> str:
        """Get full details of a product feedback item by title (partial match).

        Returns severity, area, reproduction steps, expected/actual behavior,
        evidence links, and proposed fix.
        """
        from ..db import query_rows
        rows = query_rows(db, "product_feedback")
        for row in rows:
            if title.lower() in row.get("title", "").lower():
                return (
                    f"**{row['title']}**\n\n"
                    f"- **Severity:** {row['severity']}\n"
                    f"- **Area:** {row['area']}\n"
                    f"- **Status:** {row['status']}\n\n"
                    f"**Reproduction Steps:**\n{row.get('repro_steps', 'N/A')}\n\n"
                    f"**Expected Behavior:**\n{row.get('expected', 'N/A')}\n\n"
                    f"**Actual Behavior:**\n{row.get('actual', 'N/A')}\n\n"
                    f"**Evidence Links:**\n{row.get('evidence_links_json', 'N/A')}\n\n"
                    f"**Proposed Fix:**\n{row.get('proposed_fix', 'N/A')}"
                )
        return f"No feedback item found matching '{title}'."

    @mcp.tool()
    def get_ledger_entries(limit: int = 20) -> str:
        """Get recent entries from the tamper-evident hash-chained ledger.

        Returns command, timestamp, success status, hash, and full JSON for
        each entry. The ledger provides a cryptographic audit trail of key actions.
        """
        from ..db import query_rows
        rows = query_rows(db, "run_log", order_by="sequence DESC", limit=limit)
        if not rows:
            return "No ledger entries yet."
        lines = [f"**Ledger — {len(rows)} most recent entries**\n"]
        for row in rows:
            success = "OK" if row.get("success") else "FAIL"
            lines.append(
                f"#{row['sequence']} | **{row['command']}** | {row['started_at'][:19]} | "
                f"{success} | `{row['hash'][:16]}...`"
            )
        return "\n".join(lines)

    @mcp.tool()
    def get_architecture() -> str:
        """Get the complete architecture overview of the agent system.

        Returns a detailed description of all subsystems, how they connect,
        the tech stack, safety model, and deployment pipeline.
        """
        index = _get_index()
        rag_index = _get_rag_index()
        from ..ledger import verify_chain

        chain = verify_chain(db, config)

        return f"""**revcat-agent-advocate — System Architecture**

## Tech Stack
- **Language:** Python 3.11+
- **LLM:** Claude API (Anthropic) — defaults to AI_MODEL env var; application letter hardcodes claude-opus-4-6
- **Vector DB:** ChromaDB Cloud (cosine similarity, persistent)
- **Embeddings:** all-mpnet-base-v2 (768-dim) via HF Inference API
- **Reranker:** ms-marco-MiniLM-L-12-v2 (cross-encoder) via HF Inference API
- **Database:** Turso (cloud SQLite via libsql) with local fallback
- **Search:** Hybrid BM25 (k1=1.2, b=0.75) + semantic + reranker
- **Site:** Jinja2 templates → static HTML on GitHub Pages
- **MCP:** FastMCP server (stdio + SSE transports)
- **CI/CD:** GitHub Actions (test → build-site → deploy to Pages)

## Subsystems
1. **Knowledge Engine** — Ingests RC docs (LLM index + .md mirrors), builds BM25 + RAG indexes
2. **Content Engine** — Outlines, drafts, citation verification, code snippet extraction
3. **Growth Engine** — Experiments (SEO, content series, community blitz, integration showcase)
4. **Feedback Engine** — Doc analysis, API/MCP repro testing, structured feedback
5. **Community Engine** — GitHub/Reddit/X scanning, response drafting (DRY_RUN gated)
6. **Intelligence** — Competitive analysis, doc quality scoring, ROI dashboard
7. **Ledger** — Hash-chained (SHA256), HMAC-signed, tamper-evident audit trail
8. **MCP Server** — Exposes all tools to other AI agents
9. **HTTP API** — JSON endpoints for integration
10. **Chat** — Interactive doc-grounded Q&A with slash commands
11. **Scheduler** — Autonomous 6h cycle (ingest, content, experiments, feedback, site)
12. **Distribution** — Content approval queue, publication status tracking
13. **Reliability** — Circuit breakers, ops dashboard, health monitoring

## Current State
- Docs indexed: {index.doc_count if index else 0}
- RAG chunks: {rag_index.chunk_count if hasattr(rag_index, 'chunk_count') else len(rag_index.chunks)}
- Content pieces: {count_rows(db, 'content_pieces')}
- Experiments: {count_rows(db, 'growth_experiments')}
- Feedback items: {count_rows(db, 'product_feedback')}
- Ledger entries: {chain.total_entries} ({'chain verified' if chain.valid else f'BROKEN: {len(chain.breaks)} breaks'})

## Safety Model
- DRY_RUN=true (default) — no external posts, drafts only
- ALLOW_WRITES=false (default) — read-only API access
- DEMO_MODE available — mock API responses for testing
- Key actions logged in tamper-evident ledger

## MCP Connection
```
claude mcp add revcat-agent-advocate -- revcat-advocate mcp-serve
```"""

    @mcp.tool()
    def run_experiment_mcp(name: str) -> str:
        """Start a growth experiment by name.

        Available experiments: programmatic-seo, content-series, community-blitz, integration-showcase.
        Returns experiment status and initial outputs.
        """
        from ..growth.experiments import EXPERIMENT_REGISTRY, start_experiment, get_experiment
        if name not in EXPERIMENT_REGISTRY:
            return f"Unknown experiment '{name}'. Available: {', '.join(EXPERIMENT_REGISTRY.keys())}"
        try:
            exp_id = start_experiment(db, name, {})
            exp = get_experiment(db, exp_id)
            return (
                f"**Experiment Started:** {exp['name']}\n\n"
                f"- Hypothesis: {exp['hypothesis']}\n"
                f"- Metric: {exp['metric']}\n"
                f"- Channel: {exp['channel']}\n"
                f"- Status: {exp['status']}\n\n"
                f"Run `revcat-advocate run-experiment --name {name}` for full execution with SEO generation."
            )
        except Exception as e:
            return f"Error starting experiment: {e}"

    @mcp.tool()
    def generate_feedback_mcp(count: int = 3) -> str:
        """Generate structured product feedback from documentation analysis.

        Analyzes RevenueCat docs for inconsistencies, gaps, and friction points.
        Returns feedback items with severity, repro steps, and proposed fixes.
        """
        from ..feedback.collector import generate_feedback_from_docs
        bm25_index = _get_index()
        try:
            items = generate_feedback_from_docs(bm25_index, config, db, ledger_ctx=None, count=count)
            if not items:
                return "No feedback generated. Ensure docs are ingested first."
            lines = [f"**Generated {len(items)} feedback items:**\n"]
            for item in items:
                lines.append(
                    f"- [{item.severity.upper()}] **{item.title}** ({item.area})\n"
                    f"  Repro: {item.repro_steps[:100]}...\n"
                    f"  Fix: {item.proposed_fix[:100]}..."
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error generating feedback: {e}"

    @mcp.tool()
    def get_weekly_report() -> str:
        """Generate a weekly activity report.

        Summarizes all agent activity from the past 7 days: content published,
        experiments run, feedback filed, community interactions, and ledger stats.
        """
        from ..reporting.weekly import generate_weekly_report
        try:
            report = generate_weekly_report(db, config)
            return report
        except Exception as e:
            return f"Error generating report: {e}"

    # ── Skill Runtime ──────────────────────────────────────────────────

    @mcp.tool()
    def list_skills() -> str:
        """List all available developer skills with their capabilities.

        Skills are composable tools for RevenueCat integration tasks:
        code review, migration, paywall generation, webhook debugging, etc.
        """
        from ..skills.runtime import SkillRuntime
        runtime = SkillRuntime(config, db)
        runtime.discover()
        skills = runtime.list_skills()
        if not skills:
            return "No skills discovered."
        lines = [f"**{len(skills)} skills available:**\n"]
        for s in skills:
            inputs_str = ", ".join(f"`{i['name']}`{'*' if i['required'] else ''}" for i in s["inputs"]) or "none"
            lines.append(
                f"### {s['name']} v{s['version']}\n"
                f"{s['description']}\n"
                f"- Inputs: {inputs_str}\n"
                f"- Scopes: {', '.join(s['scopes'])}\n"
                f"- Chains to: {', '.join(s['chains_to']) or 'none'}"
            )
        return "\n\n".join(lines)

    @mcp.tool()
    def run_skill(skill_name: str, inputs_json: str = "{}") -> str:
        """Prepare a skill's context, prompt, and scoped tools for the caller to drive.

        Validates inputs, checks permission scopes, and returns the skill's prompt
        and available tools. The caller (CLI, MCP client, or agent) drives the
        actual LLM tool-use cycle. Use list_skills() first to see available skills.

        Args:
            skill_name: Name of the skill (e.g. "review-rc", "search-docs", "debug-webhook")
            inputs_json: JSON string of input parameters matching the skill's declared schema
        """
        import json
        from ..skills.runtime import SkillRuntime
        runtime = SkillRuntime(config, db)
        runtime.discover()
        try:
            inputs = json.loads(inputs_json) if inputs_json else {}
        except json.JSONDecodeError as e:
            return f"Invalid JSON inputs: {e}"
        result = runtime.execute(skill_name, inputs)
        if not result.success:
            return f"Skill '{skill_name}' failed:\n" + "\n".join(f"- {e}" for e in result.errors)
        parts = [
            f"**Skill:** {result.skill}",
            f"**Duration:** {result.duration_ms}ms",
            f"**Scopes:** {', '.join(result.scopes_used)}",
            f"**Tools:** {', '.join(result.output.get('tools_available', []))}",
        ]
        if result.output.get("doc_context"):
            parts.append(f"\n**Doc context ({len(result.output['doc_context'])} results):**")
            for doc in result.output["doc_context"]:
                parts.append(f"- [{doc['title']}]({doc['url']})")
        if result.output.get("prompt"):
            parts.append(f"\n**Prompt loaded:** {len(result.output['prompt'])} chars")
        return "\n".join(parts)

    @mcp.tool()
    def run_skill_chain(skill_names: str, inputs_json: str = "{}") -> str:
        """Execute a chain of skills in sequence, passing context forward.

        Skills declared with chains_to/chains_from are designed to compose.
        Example: "search-docs,review-rc,rc-audit"

        Args:
            skill_names: Comma-separated skill names to chain
            inputs_json: JSON string of initial input parameters
        """
        import json
        from ..skills.runtime import SkillRuntime
        runtime = SkillRuntime(config, db)
        runtime.discover()
        names = [n.strip() for n in skill_names.split(",") if n.strip()]
        if len(names) < 2:
            return "Chain requires at least 2 skills. Provide comma-separated names."
        try:
            inputs = json.loads(inputs_json) if inputs_json else {}
        except json.JSONDecodeError as e:
            return f"Invalid JSON inputs: {e}"
        try:
            chain = runtime.chain(names)
        except Exception as e:
            return f"Chain validation failed: {e}"
        result = chain.run(inputs)
        if not result.success:
            return "Chain failed:\n" + "\n".join(f"- {e}" for e in result.errors)
        return (
            f"**Chain completed:** {' → '.join(names)}\n"
            f"**Scopes used:** {', '.join(result.output.get('scopes_used', []))}\n"
            f"**Steps:** {len(result.output.get('chain_results', []))}"
        )

    # ── Resources ─────────────────────────────────────────────────────

    @mcp.resource("advocate://stats")
    def resource_stats() -> str:
        """Current agent statistics."""
        return get_agent_stats()

    @mcp.resource("advocate://architecture")
    def resource_architecture() -> str:
        """Full system architecture."""
        return get_architecture()

    @mcp.resource("advocate://readme")
    def resource_readme() -> str:
        """Agent README and capabilities overview."""
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        readme_path = os.path.join(repo_root, "README.md")
        if os.path.exists(readme_path):
            with open(readme_path, "r") as f:
                return f.read()
        return "README.md not found."

    return mcp
