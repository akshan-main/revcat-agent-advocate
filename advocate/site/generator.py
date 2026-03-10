import json
import os
import shutil
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from ..db import query_rows
from ..ledger import verify_chain


def _extract_github_repo(url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL like https://github.com/owner/repo/issues/123."""
    import re
    m = re.search(r'github\.com/([^/]+/[^/]+)', url)
    return m.group(1) if m else ""


def _extract_subreddit(url: str) -> str:
    """Extract subreddit name from a Reddit URL like https://reddit.com/r/subreddit/..."""
    import re
    m = re.search(r'/r/([^/]+)', url)
    return m.group(1) if m else ""


def _md_to_html(md_text: str, base_url: str = "") -> Markup:
    """Convert markdown to HTML using the markdown library. Returns Markup (safe for Jinja2)."""
    import re
    import markdown
    # Strip YAML front matter
    if md_text.startswith("---"):
        parts = md_text.split("---", 2)
        if len(parts) >= 3:
            md_text = parts[2]
    # Strip duplicate front matter in yaml code blocks (writer artifact)
    md_text = re.sub(r'^(\s*)```ya?ml\s*\n---\n.*?\n---\n```', '', md_text.lstrip(), count=1, flags=re.DOTALL)
    md_text = md_text.lstrip()
    # Strip leading H1 (template already renders the title as H1)
    md_text = re.sub(r'^#\s+[^\n]+\n*', '', md_text, count=1)
    html = markdown.markdown(
        md_text,
        extensions=["fenced_code", "tables", "toc"],
    )
    # Normalize absolute GitHub Pages URLs to relative paths first
    # This ensures the site works regardless of who deploys it
    html = re.sub(
        r'href="https?://[^"]*\.github\.io/[^"/]*/((content|experiments|feedback|runbook|apply|twitter-bot|issues|scorecard|research)(?:/[^"]*)?)"',
        r'href="/\1"',
        html,
    )
    # Fix relative RevenueCat doc links to full URLs
    html = re.sub(
        r'href="/((?:migrating|getting-started|sdk-guides|dashboard|customers|test|tools|webhooks|integrations|offerings|paywalls|billing|charts|api-v2|entitlements)[^"]*)"',
        r'href="https://www.revenuecat.com/docs/\1"',
        html,
    )
    # Rewrite internal links (e.g. /content/ -> /revcat-agent-advocate/content/)
    if base_url:
        html = re.sub(
            r'href="/((?:content|experiments|feedback|runbook|apply|twitter-bot|issues|scorecard|research)(?:/[^"]*)?)"',
            f'href="{base_url}/\\1"',
            html,
        )
    return Markup(html)


def _build_doc_index_json(cache_dir: str, db_conn) -> list[dict]:
    """Build a condensed doc index for the issue helper page.

    Returns a list of {title, url, summary} dicts — one per cached doc page.
    This gets embedded as JSON in the page so the client-side JS can send it
    to Claude as context.
    """
    import re
    pages_dir = os.path.join(cache_dir, "pages")
    if not os.path.isdir(pages_dir):
        return []

    index = []
    doc_snapshots = query_rows(db_conn, "doc_snapshots", order_by="url ASC")
    url_map = {s.get("path", ""): s.get("url", "") for s in doc_snapshots}

    for fname in sorted(os.listdir(pages_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(pages_dir, fname)
        try:
            with open(fpath, "r") as f:
                content = f.read(2000)  # Only first 2KB for summary
        except Exception:
            continue

        # Extract title
        title_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else fname.replace(".md", "").replace("-", " ").title()

        # Extract first paragraph as summary
        lines = content.split("\n")
        summary_lines = []
        in_front_matter = False
        for line in lines:
            if line.strip() == "---":
                in_front_matter = not in_front_matter
                continue
            if in_front_matter or line.startswith("#"):
                continue
            stripped = line.strip()
            if not stripped:
                if summary_lines:
                    break
                continue
            summary_lines.append(stripped)
            if len(summary_lines) >= 2:
                break

        summary = " ".join(summary_lines)
        if len(summary) > 200:
            summary = summary[:197] + "..."

        # Find URL from doc_snapshots
        doc_path = fname.replace(".md", "")
        url = url_map.get(doc_path, f"https://www.revenuecat.com/docs/{doc_path}")

        if summary:
            index.append({"title": title, "url": url, "summary": summary})

    return index


def _build_doc_categories(cache_dir: str) -> list[dict]:
    """Group cached docs by category for the issue helper display."""
    pages_dir = os.path.join(cache_dir, "pages")
    if not os.path.isdir(pages_dir):
        return []

    categories = {}
    for fname in os.listdir(pages_dir):
        if not fname.endswith(".md"):
            continue
        # Infer category from filename prefix (e.g. "sdk-guides-ios.md" -> "sdk guides")
        parts = fname.replace(".md", "").split("-")
        cat = parts[0] if parts else "other"
        # Map common prefixes
        cat_map = {
            "getting": "Getting Started", "sdk": "SDK", "api": "API",
            "dashboard": "Dashboard", "charts": "Charts", "paywalls": "Paywalls",
            "offerings": "Offerings", "billing": "Billing", "migration": "Migration",
            "integrations": "Integrations", "test": "Testing", "tools": "Tools",
            "customers": "Customers", "webhooks": "Webhooks", "entitlements": "Entitlements",
        }
        cat_name = cat_map.get(cat, cat.title())
        categories[cat_name] = categories.get(cat_name, 0) + 1

    return sorted([{"name": k, "count": v} for k, v in categories.items()], key=lambda x: -x["count"])


def _load_doc_snippets(sources: list, cache_dir: str) -> list[dict]:
    """Load doc snippet previews from cache for each source URL.

    Returns a list of {url, title, preview} dicts for the template.
    """
    import re
    snippets = []
    pages_dir = os.path.join(cache_dir, "pages")
    if not os.path.isdir(pages_dir):
        return snippets

    for source in sources:
        url = source.get("url", source) if isinstance(source, dict) else str(source)
        if not url:
            continue

        # Extract doc path from URL to find cached file
        # URL like https://www.revenuecat.com/docs/some-page -> some-page.md
        path_match = re.search(r'revenuecat\.com/docs/(.+?)(?:\?|#|$)', url)
        if not path_match:
            continue
        doc_path = path_match.group(1).rstrip("/")
        # Try common cache filename patterns
        candidates = [
            os.path.join(pages_dir, doc_path + ".md"),
            os.path.join(pages_dir, doc_path.replace("/", "__") + ".md"),
            os.path.join(pages_dir, doc_path.replace("/", "-") + ".md"),
            os.path.join(pages_dir, doc_path.split("/")[-1] + ".md"),
        ]
        content = None
        for candidate in candidates:
            if os.path.exists(candidate):
                try:
                    with open(candidate, "r") as f:
                        content = f.read()
                    break
                except Exception:
                    pass

        if not content:
            continue

        # Extract title from first H1
        title_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else doc_path.replace("-", " ").title()

        # Extract first meaningful paragraph (skip front matter, headings, blank lines)
        lines = content.split("\n")
        preview_lines = []
        in_front_matter = False
        for line in lines:
            if line.strip() == "---":
                in_front_matter = not in_front_matter
                continue
            if in_front_matter:
                continue
            if line.startswith("#"):
                continue
            stripped = line.strip()
            if not stripped:
                if preview_lines:
                    break  # stop at first blank line after content
                continue
            # Skip markdown directives (:::success, :::warning, etc.)
            if stripped.startswith(":::"):
                continue
            # Strip markdown link syntax to plain text
            cleaned = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', stripped)
            preview_lines.append(cleaned)
            if len(preview_lines) >= 4:
                break

        preview = " ".join(preview_lines)
        if len(preview) > 300:
            preview = preview[:297] + "..."

        if preview:
            snippets.append({"url": url, "title": title, "preview": preview})

    return snippets


def _build_scorecard_stats(db_conn, chain, docs_indexed: int) -> dict:
    """Build aggregate stats for the scorecard page."""
    from ..db import count_rows
    total_runs = count_rows(db_conn, "run_log")
    failed_runs = count_rows(db_conn, "run_log", where={"success": 0})
    succeeded = total_runs - failed_runs
    success_rate = round((succeeded / total_runs * 100) if total_runs > 0 else 0)

    content_all = query_rows(db_conn, "content_pieces")
    content_non_apply = [c for c in content_all if c.get("slug") != "application-letter"]
    content_verified = sum(1 for c in content_non_apply if c.get("status") == "verified")
    content_draft = sum(1 for c in content_non_apply if c.get("status") == "draft")

    total_words = sum(c.get("word_count", 0) for c in content_all)
    total_citations = sum(c.get("citations_count", 0) for c in content_all)

    experiments = query_rows(db_conn, "growth_experiments")
    exp_concluded = sum(1 for e in experiments if e.get("status") == "concluded")
    exp_running = sum(1 for e in experiments if e.get("status") == "running")

    feedback_all = query_rows(db_conn, "product_feedback")
    fb_major = sum(1 for f in feedback_all if f.get("severity") in ("critical", "major"))
    fb_minor = sum(1 for f in feedback_all if f.get("severity") in ("minor", "suggestion"))

    tweets = query_rows(db_conn, "community_interactions", where={"channel": "twitter"})
    tweets_sent = sum(1 for t in tweets if t.get("status") == "sent")
    tweets_draft = sum(1 for t in tweets if t.get("status") == "draft")

    _min_row = db_conn.execute("SELECT MIN(started_at) as v FROM run_log").fetchone()
    _max_row = db_conn.execute("SELECT MAX(started_at) as v FROM run_log").fetchone()
    first_run = (_min_row["v"] if _min_row else "") or ""
    last_run = (_max_row["v"] if _max_row else "") or ""

    days_active = 1
    if first_run and last_run:
        from datetime import datetime
        try:
            d1 = datetime.fromisoformat(first_run.replace("Z", "+00:00"))
            d2 = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            days_active = max(1, (d2 - d1).days + 1)
        except Exception:
            pass

    return {
        "total_runs": total_runs,
        "success_rate": success_rate,
        "total_words": total_words,
        "total_citations": total_citations,
        "docs_indexed": docs_indexed,
        "chain_valid": chain.valid if hasattr(chain, "valid") else chain.get("valid", True),
        "chain_entries": chain.total_entries if hasattr(chain, "total_entries") else chain.get("total_entries", 0),
        "chain_breaks": len(chain.breaks) if hasattr(chain, "breaks") else len(chain.get("breaks", [])),
        "content_count": len(content_non_apply),
        "content_verified": content_verified,
        "content_draft": content_draft,
        "seo_count": count_rows(db_conn, "seo_pages"),
        "experiment_count": len(experiments),
        "experiments_concluded": exp_concluded,
        "experiments_running": exp_running,
        "feedback_count": len(feedback_all),
        "feedback_major": fb_major,
        "feedback_minor": fb_minor,
        "tweet_count": len(tweets),
        "tweets_sent": tweets_sent,
        "tweets_draft": tweets_draft,
        "first_run": first_run,
        "last_run": last_run,
        "days_active": days_active,
    }


def _build_command_stats(db_conn) -> list[dict]:
    """Build per-command run statistics."""
    rows = db_conn.execute(
        "SELECT command, COUNT(*) as total, SUM(success) as succeeded "
        "FROM run_log GROUP BY command ORDER BY COUNT(*) DESC"
    ).fetchall()
    result = []
    for r in rows:
        total = r["total"]
        succeeded = r["succeeded"] or 0
        failed = total - succeeded
        rate = round((succeeded / total * 100) if total > 0 else 0)
        result.append({
            "command": r["command"],
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "rate": rate,
        })
    return result


def build_site(db_conn, config, clean: bool = False):
    """Build the complete static site from DB and artifacts.

    Args:
        db_conn: Database connection.
        config: Application config.
        clean: If True, wipe site_output before rendering so the deploy
               reflects DB truth only (no stale files from previous builds).
    """
    output_dir = config.site_output_dir
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")

    # Clean build: remove entire output dir so deploy is DB-truth only
    if clean and os.path.isdir(output_dir):
        shutil.rmtree(output_dir)

    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=select_autoescape(["html"]))

    # Custom filter: render feedback text as light markdown → HTML
    from markupsafe import Markup as _Markup
    import re as _re
    import markdown as _md
    def nl2br(value):
        # Use markdown library to render bold, code, blockquotes, links, lists
        # Strip :::info, :::warning, :::success, ::: callout markers from RC docs
        text = _re.sub(r':::\w*\s*', '', str(value))
        # Ensure a blank line before list items so markdown parses them as lists
        text = _re.sub(r'([^\n])\n(- )', r'\1\n\n\2', text)
        html = _md.markdown(text, extensions=["fenced_code"])
        # Fix relative RevenueCat doc links (e.g. /migrating-to-revenuecat/...) to full URLs
        html = _re.sub(
            r'href="/((?:migrating|getting-started|sdk-guides|dashboard|customers|test|tools|webhooks|integrations|offerings|paywalls|billing|charts|api-v2|entitlements)[^"]*)"',
            r'href="https://www.revenuecat.com/docs/\1"',
            html,
        )
        return _Markup(html)
    env.filters["nl2br"] = nl2br

    def tweet_nl2br(value):
        """Convert literal \\n in tweet text to <br> tags."""
        text = str(value).replace("\\n", "\n")
        # Escape HTML, then convert newlines to <br>
        from markupsafe import escape as _escape
        escaped = _escape(text)
        return _Markup(str(escaped).replace("\n", "<br>"))
    env.filters["tweet_nl2br"] = tweet_nl2br

    # Verify ledger chain
    chain = verify_chain(db_conn, config)
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Base URL for GitHub Pages project sites (e.g. "/revcat-agent-advocate")
    base_url = config.site_base_url.rstrip("/") if config.site_base_url else ""

    # Compute docs_indexed once for all pages
    from ..db import count_rows
    from ..knowledge.search import build_index as _build_index
    try:
        _idx = _build_index(config.docs_cache_dir, db_conn)
        docs_indexed = _idx.doc_count
    except Exception:
        docs_indexed = 0

    # Shared context
    shared = {
        "chain_status": chain,
        "site_title": "revcat-agent-advocate",
        "build_date": build_date,
        "base_url": base_url,
        "search_api_url": config.search_api_url or "",
    }

    # When base_url is set, nest output under that subpath so local server matches GitHub Pages
    if base_url:
        subpath = base_url.lstrip("/")
        site_dir = os.path.join(output_dir, subpath)
    else:
        site_dir = output_dir

    # Ensure output dirs
    for subdir in ["apply", "content", "experiments", "feedback", "runbook", "assets", "twitter-bot", "issues", "scorecard", "research"]:
        os.makedirs(os.path.join(site_dir, subdir), exist_ok=True)

    # Root redirect (at site_output/index.html)
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(f'<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url={base_url}/apply/"></head><body><a href="{base_url}/apply/">Apply</a></body></html>')

    # Subpath redirect (at site_output/revcat-agent-advocate/index.html)
    if base_url:
        with open(os.path.join(site_dir, "index.html"), "w") as f:
            f.write(f'<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url={base_url}/apply/"></head><body><a href="{base_url}/apply/">Apply</a></body></html>')

    # 2. Apply page — gather real stats from DB
    from ..__init__ import __version__ as _v  # noqa
    all_content = query_rows(db_conn, "content_pieces")
    content_verified = sum(1 for c in all_content if c.get("status") == "verified")
    content_draft = sum(1 for c in all_content if c.get("status") == "draft" and c.get("slug") != "application-letter")
    apply_stats = {
        "content_verified": content_verified,
        "content_draft": content_draft,
        "seo_pages": count_rows(db_conn, "seo_pages"),
        "experiments": count_rows(db_conn, "growth_experiments"),
        "feedback": count_rows(db_conn, "product_feedback"),
    }

    apply_content = query_rows(db_conn, "content_pieces", where={"slug": "application-letter"})
    apply_html = ""
    if apply_content:
        apply_html = _md_to_html(apply_content[0].get("body_md", ""), base_url)
    template = env.get_template("apply.html")
    _apply_template = template
    _apply_html = apply_html
    _apply_stats = apply_stats

    # Render apply page with real stats
    with open(os.path.join(site_dir, "apply", "index.html"), "w") as f:
        f.write(_apply_template.render(**shared, page_title="Application", content=_apply_html, stats=_apply_stats))

    # 4. Content pages
    content_pieces = [p for p in query_rows(db_conn, "content_pieces", order_by="created_at DESC") if p.get("slug") != "application-letter"]
    seo_pages = query_rows(db_conn, "seo_pages", order_by="created_at DESC")
    template = env.get_template("content.html")
    with open(os.path.join(site_dir, "content", "index.html"), "w") as f:
        f.write(template.render(**shared, page_title="Content", content_pieces=content_pieces, seo_pages=seo_pages))

    # Individual content pages
    detail_template = env.get_template("content_detail.html")
    all_slugs = []
    for piece in content_pieces:
        slug = piece["slug"]
        all_slugs.append(slug)
        slug_out = os.path.join(site_dir, "content", slug)
        os.makedirs(slug_out, exist_ok=True)
        body_html = _md_to_html(piece.get("body_md", ""), base_url)
        sources = json.loads(piece["sources_json"]) if piece.get("sources_json") else []
        verification = json.loads(piece["verification_json"]) if piece.get("verification_json") else {}
        doc_snippets = _load_doc_snippets(sources, config.docs_cache_dir)
        with open(os.path.join(slug_out, "index.html"), "w") as f:
            f.write(detail_template.render(
                **shared, page_title=piece.get("title", slug),
                piece=piece, body_html=body_html,
                sources=sources, verification=verification,
                doc_snippets=doc_snippets,
            ))

    # SEO pages as content detail too
    for page in seo_pages:
        slug = page["slug"]
        all_slugs.append(slug)
        slug_out = os.path.join(site_dir, "content", slug)
        os.makedirs(slug_out, exist_ok=True)
        body_html = _md_to_html(page.get("body_md", ""), base_url)
        seo_sources = json.loads(page["sources_json"]) if page.get("sources_json") else []
        with open(os.path.join(slug_out, "index.html"), "w") as f:
            f.write(detail_template.render(
                **shared, page_title=page.get("title", slug),
                piece=page, body_html=body_html,
                sources=seo_sources, verification={},
            ))

    # Clean up orphan content dirs not in DB
    content_dir = os.path.join(site_dir, "content")
    if os.path.isdir(content_dir):
        for entry in os.listdir(content_dir):
            entry_path = os.path.join(content_dir, entry)
            if os.path.isdir(entry_path) and entry not in all_slugs:
                shutil.rmtree(entry_path)

    # 5. Experiments page
    experiments = query_rows(db_conn, "growth_experiments", order_by="created_at DESC")
    for exp in experiments:
        for field in ["inputs_json", "outputs_json", "results_json"]:
            if exp.get(field) and isinstance(exp[field], str):
                try:
                    exp[field] = json.loads(exp[field])
                except json.JSONDecodeError:
                    pass
    # Build slug→title map so experiment artifact links show real titles
    slug_titles = {p["slug"]: p["title"] for p in content_pieces}
    for sp in seo_pages:
        slug_titles[sp["slug"]] = sp["title"]

    template = env.get_template("experiments.html")
    with open(os.path.join(site_dir, "experiments", "index.html"), "w") as f:
        f.write(template.render(**shared, page_title="Experiments", experiments=experiments, json=json, slug_titles=slug_titles))

    # 6. Feedback page
    feedback_rows = query_rows(db_conn, "product_feedback", order_by="created_at DESC")
    for fb in feedback_rows:
        if fb.get("evidence_links_json") and isinstance(fb["evidence_links_json"], str):
            try:
                fb["evidence_links_json"] = json.loads(fb["evidence_links_json"])
            except json.JSONDecodeError:
                pass
    template = env.get_template("feedback.html")
    with open(os.path.join(site_dir, "feedback", "index.html"), "w") as f:
        f.write(template.render(**shared, page_title="Product Feedback", feedbacks=feedback_rows))

    # 6b. Twitter Bot page
    all_interactions = query_rows(db_conn, "community_interactions", order_by="created_at DESC")
    from ..social.twitter import AGENT_SYSTEM_PROMPT as TWEET_AGENT_PROMPT

    # Use tweet drafts from DB (community_interactions with channel=twitter)
    # instead of live Twitter API calls to keep builds deterministic
    tweet_interactions = [i for i in all_interactions if i.get("channel") == "twitter"]
    tweets_data = []
    for ti in tweet_interactions[:50]:
        tweets_data.append({
            "id": ti.get("id", ""),
            "text": ti.get("draft_response", ""),
            "created_at": (ti.get("created_at") or "")[:10],
            "status": ti.get("status", "draft"),
            "critic_verdict": ti.get("notes", ""),
            "topic": ti.get("question", ""),
        })

    # Fallback: extract tweets from agent-cycle run_log tool calls
    # (agent cycles post tweets but don't always log to community_interactions)
    if not tweets_data:
        import json as _json_mod
        tweet_runs = query_rows(db_conn, "run_log",
                                where={"command": "agent-cycle"},
                                order_by="sequence ASC")
        for run in tweet_runs:
            tool_calls = []
            if run.get("tool_calls_json"):
                try:
                    tool_calls = _json_mod.loads(run["tool_calls_json"])
                except (ValueError, TypeError):
                    pass
            for tc in tool_calls:
                if tc.get("tool") in ("agent.post_tweet",):
                    # Extract tweet text from params_summary
                    ps = tc.get("params_summary", "")
                    # params_summary may be truncated JSON: {"topic": "text..."}
                    tweet_text = ps
                    try:
                        parsed = _json_mod.loads(ps)
                        tweet_text = parsed.get("topic", ps)
                    except (ValueError, TypeError):
                        # Truncated JSON — extract text after {"topic": "
                        import re
                        m = re.search(r'"topic":\s*"(.+)', ps)
                        if m:
                            tweet_text = m.group(1).rstrip('"} ')
                        elif ps.startswith('{'):
                            tweet_text = ps  # keep as-is
                    if tweet_text:
                        tweets_data.append({
                            "id": "",
                            "text": tweet_text[:280],
                            "created_at": (run.get("started_at") or "")[:10],
                            "status": "posted" if tc.get("result_summary") else "draft",
                        })

    twitter_bot_template = env.get_template("twitter_bot.html")
    with open(os.path.join(site_dir, "twitter-bot", "index.html"), "w") as f:
        f.write(twitter_bot_template.render(
            **shared,
            page_title="Twitter Agent",
            tweets_data=tweets_data,
            agent_prompt=TWEET_AGENT_PROMPT,
            docs_indexed=docs_indexed,
        ))

    # 6c. Issue Helper page — interactive doc-grounded issue answerer
    doc_index_for_helper = _build_doc_index_json(config.docs_cache_dir, db_conn)
    doc_categories = _build_doc_categories(config.docs_cache_dir)
    issue_helper_template = env.get_template("issue_helper.html")
    with open(os.path.join(site_dir, "issues", "index.html"), "w") as f:
        f.write(issue_helper_template.render(
            **shared,
            page_title="Issue Helper",
            doc_count=docs_indexed,
            doc_index_json=json.dumps(doc_index_for_helper),
            doc_categories=doc_categories,
        ))

    # 6d. Scorecard page — live operational metrics from DB
    scorecard_stats = _build_scorecard_stats(db_conn, chain, docs_indexed)
    command_stats = _build_command_stats(db_conn)
    failed_runs = [dict(r) for r in query_rows(db_conn, "run_log", where={"success": 0}, order_by="started_at DESC")]
    scorecard_template = env.get_template("scorecard.html")
    with open(os.path.join(site_dir, "scorecard", "index.html"), "w") as f:
        f.write(scorecard_template.render(
            **shared,
            page_title="Scorecard",
            stats=scorecard_stats,
            command_stats=command_stats,
            failed_runs=failed_runs[:10],
        ))

    # 6e. Research Workflow page
    # Agent cycles from run_log
    agent_cycle_rows = query_rows(
        db_conn, "run_log",
        order_by="started_at DESC",
    )
    agent_cycle_rows = [
        r for r in agent_cycle_rows
        if r.get("command") in ("agent-cycle", "auto")
    ]
    agent_cycles = []
    for run in agent_cycle_rows:
        # Extract what the agent observed and decided from tool_calls_json
        observed = ""
        decided = ""
        produced = ""
        tool_calls = []
        if run.get("tool_calls_json"):
            try:
                tool_calls = json.loads(run["tool_calls_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        scan_tools = [tc for tc in tool_calls if "scan" in tc.get("tool", "").lower() or "search" in tc.get("tool", "").lower()]
        action_tools = [tc for tc in tool_calls if any(k in tc.get("tool", "").lower() for k in ("write", "tweet", "post", "feedback", "respond"))]

        if scan_tools:
            observed = ", ".join(tc.get("tool", "").split(".")[-1] for tc in scan_tools[:3])
        elif tool_calls:
            observed = tool_calls[0].get("tool", "").split(".")[-1] if tool_calls else "—"
        else:
            observed = "—"

        if action_tools:
            decided = ", ".join(tc.get("tool", "").split(".")[-1] for tc in action_tools[:2])
        elif len(tool_calls) > 1:
            decided = tool_calls[-1].get("tool", "").split(".")[-1]
        else:
            decided = "—"

        # Check outputs
        if run.get("outputs_json"):
            try:
                outputs = json.loads(run["outputs_json"])
                if isinstance(outputs, dict):
                    produced = outputs.get("summary", outputs.get("result", ""))[:80]
            except (json.JSONDecodeError, TypeError):
                pass

        agent_cycles.append({
            "started_at": run.get("started_at", ""),
            "command": run.get("command", ""),
            "observed": observed,
            "decided": decided,
            "produced": produced,
            "success": run.get("success", 0),
        })

    # Community signals (non-twitter interactions)
    all_signals = query_rows(db_conn, "community_interactions", order_by="created_at DESC")
    signals = [s for s in all_signals if s.get("channel") in ("github", "reddit", "stackoverflow", "discord", "other")]
    signal_count = len(signals)
    response_count = sum(1 for s in signals if s.get("draft_response"))

    # Content produced (exclude application letter)
    produced_content = [
        p for p in query_rows(db_conn, "content_pieces", order_by="created_at DESC")
        if p.get("slug") != "application-letter"
    ]
    content_from_research = len(produced_content)

    research_template = env.get_template("research.html")
    with open(os.path.join(site_dir, "research", "index.html"), "w") as f:
        f.write(research_template.render(
            **shared,
            page_title="Research Workflow",
            agent_cycles=agent_cycles,
            signals=signals[:30],
            produced_content=produced_content,
            signal_count=signal_count,
            response_count=response_count,
            content_from_research=content_from_research,
            cycle_count=len(agent_cycles),
        ))

    # 7. Runbook page (with skills data)
    skills = []
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".claude", "skills")
    if os.path.isdir(skills_dir):
        for skill_name in sorted(os.listdir(skills_dir)):
            skill_md = os.path.join(skills_dir, skill_name, "SKILL.md")
            if os.path.exists(skill_md):
                with open(skill_md) as sf:
                    lines = sf.readlines()
                desc = ""
                for line in lines:
                    if line.startswith("description:"):
                        desc = line.split("description:", 1)[1].strip()
                        break
                skills.append({"name": skill_name, "description": desc})

    template = env.get_template("runbook.html")
    with open(os.path.join(site_dir, "runbook", "index.html"), "w") as f:
        f.write(template.render(**shared, page_title="Runbook", skills=skills))

    # 8. Copy CSS
    src_css = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(src_css):
        shutil.copy2(src_css, os.path.join(site_dir, "assets", "style.css"))

    # 9. Generate sitemap.xml
    base_url = ""
    if config.has_github:
        parts = config.github_repo.split("/")
        if len(parts) >= 2:
            base_url = f"https://{parts[0]}.github.io/{parts[1]}"
    _generate_sitemap(output_dir, base_url, all_slugs, build_date)

    # 10. Generate robots.txt
    _generate_robots(output_dir, base_url)

    # Count actual generated pages
    page_count = 0
    for _root, _dirs, _files in os.walk(output_dir):
        page_count += _files.count("index.html")
    return page_count


def _generate_sitemap(output_dir: str, base_url: str, content_slugs: list[str], build_date: str):
    """Generate sitemap.xml for search engines."""
    pages = [
        ("", "1.0"),
        ("apply/", "1.0"),
        ("content/", "0.9"),
        ("experiments/", "0.7"),
        ("feedback/", "0.7"),
        ("twitter-bot/", "0.8"),
        ("issues/", "0.9"),
        ("scorecard/", "0.8"),
        ("research/", "0.7"),
        ("runbook/", "0.5"),
    ]
    for slug in content_slugs:
        pages.append((f"content/{slug}/", "0.8"))

    urls = []
    for path, priority in pages:
        urls.append(
            f"  <url>\n"
            f"    <loc>{base_url}/{path}</loc>\n"
            f"    <lastmod>{build_date[:10]}</lastmod>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n"
        '</urlset>\n'
    )

    with open(os.path.join(output_dir, "sitemap.xml"), "w") as f:
        f.write(sitemap)


def _generate_robots(output_dir: str, base_url: str):
    """Generate robots.txt."""
    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    with open(os.path.join(output_dir, "robots.txt"), "w") as f:
        f.write(robots)
