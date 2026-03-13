"""Event-driven supervisor: observe → decide → act → learn.

Single cycle (cron) or daemon mode (--daemon). Signal-first architecture
with deterministic action mapping and LLM fallback for novel signals.
"""
import json
import time
import traceback
from datetime import datetime, timezone

from ..config import Config
from ..db import DBConnection, init_db_from_config, insert_row, now_iso
from ..ledger import start_run, finalize_run, log_tool_call, LedgerOutputs
from .signals import (
    ensure_signals_schema,
    decay_freshness,
    run_all_producers,
    claim_top_signal,
    mark_acted,
    mark_skipped,
    get_signal_stats,
)
from .bandit import (
    ensure_bandit_schema,
    pull_arm,
    sync_rewards_from_devto,
    get_topic_for_category,
)


ACTION_MAP = {
    "new_issue": "draft_community_response",
    "pain_point": "draft_community_response",
    "product_mention": "draft_community_response",
    "engagement_spike": "write_content",
    "engagement_drop": "skip",
    "doc_gap": "write_content",
    "trending_topic": "write_content",
    "content_due": "write_content",
    "tweet_due": "draft_tweet",
    "feedback_due": "generate_feedback",
    "scheduled_task": "write_content",
    "manual_goal": None,  # LLM decides based on issue body
    "site_stale": "rebuild_site",
}

BROWSER_ENRICHABLE = {"draft_community_response", "write_content"}


class Supervisor:

    def __init__(self, config: Config, db_conn: DBConnection | None = None):
        self.config = config
        self.db = db_conn or init_db_from_config(config)

    def run_daemon(self, interval_seconds: int = 21600, max_actions: int = 3, console=None):
        if console:
            console.print(f"[bold]Supervisor daemon started[/bold] (interval={interval_seconds}s)")

        cycle_num = 0
        while True:
            cycle_num += 1
            if console:
                console.print(f"\n{'='*50}")
                console.print(f"[bold]Cycle #{cycle_num}[/bold] — {now_iso()}")

            try:
                result = self.run_cycle(max_actions=max_actions, console=console)
                if console:
                    console.print(f"Cycle #{cycle_num} done: {result['summary'][:200]}")
            except Exception as e:
                if console:
                    console.print(f"[red]Cycle #{cycle_num} error: {e}[/red]")

            next_time = datetime.now(timezone.utc)
            if console:
                from datetime import timedelta
                next_run = next_time + timedelta(seconds=interval_seconds)
                console.print(f"Next cycle: {next_run.strftime('%H:%M:%S UTC')}")

            try:
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                if console:
                    console.print("\n[dim]Supervisor stopped.[/dim]")
                break

    def run_task_issue(self, title: str, body: str, issue_number: str = "",
                       console=None) -> dict:
        """Execute an agent-task issue directly. No producer ingestion, no scoring queue.

        Injects the task as a signal, claims it immediately, decides + executes the action,
        and returns whether the task was actually acted on.
        """
        ensure_signals_schema(self.db)
        ensure_bandit_schema(self.db)

        from .signals import ingest_signal, mark_acted, mark_skipped

        issue_url = ""
        if self.config.github_repo and issue_number:
            issue_url = f"https://github.com/{self.config.github_repo}/issues/{issue_number}"

        # Delete any previous signal for this issue so task-issues can always re-run
        if issue_url:
            self.db.execute("DELETE FROM signals WHERE url = ? AND source = 'github'", (issue_url,))
            self.db.commit()

        signal_id = ingest_signal(
            self.db,
            source="github",
            signal_type="manual_goal",
            title=title,
            body=body,
            url=issue_url,
            metadata={"repo": self.config.github_repo or "", "number": issue_number, "labels": ["agent-task"]},
            impact=1.0,
            urgency=1.0,
            confidence=1.0,
            ttl_hours=24,
        )

        if not signal_id:
            return {"acted": False, "reason": "signal deduplication — task already ingested"}

        # Claim directly by ID (no scoring/queue needed)
        self.db.execute(
            "UPDATE signals SET status = 'claimed', claimed_by = 'task-issue' WHERE id = ?",
            (signal_id,),
        )
        self.db.commit()

        signal = dict(self.db.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ).fetchone())

        action = self._decide_action(signal)

        if console:
            console.print(f"  Action decided: {action}")

        if action == "skip":
            mark_skipped(self.db, signal_id, "action decided as skip")
            return {"acted": False, "reason": "action decided as skip"}

        if not self._firewall_check(action, console):
            mark_skipped(self.db, signal_id, f"firewall denied: {action}")
            return {"acted": False, "reason": f"firewall denied: {action}"}

        if console:
            console.print(f"[bold green]ACT[/bold green] — Executing: {action}")

        outcome = self._execute_action(action, signal, console)
        mark_acted(self.db, signal_id, action, outcome)

        success = self._is_task_success(action, outcome)
        reason = outcome.get("reason") or outcome.get("error") or outcome.get("status", "unknown")
        return {"acted": success, "action": action, "outcome": outcome, "reason": reason}

    def _is_task_success(self, action: str, outcome: dict) -> bool:
        """Task-issue success must represent actual completion, not just non-error execution."""
        status = outcome.get("status")
        if status in ("error", "skipped"):
            return False

        # Form submissions are high-stakes; require an explicit submit attempt.
        if action == "submit_form":
            return (
                status == "submitted"
                and bool(outcome.get("submit_attempted"))
            )

        return True

    def run_cycle(self, max_actions: int = 3, console=None) -> dict:
        ensure_signals_schema(self.db)
        ensure_bandit_schema(self.db)

        result = {
            "signals_ingested": {},
            "actions_taken": [],
            "actions_skipped": 0,
            "summary": "",
            "started_at": now_iso(),
        }

        if console:
            console.print("[bold cyan]OBSERVE[/bold cyan] — Ingesting signals...")

        decay_freshness(self.db)
        ingestion = run_all_producers(self.db, self.config)
        result["signals_ingested"] = ingestion

        if console:
            console.print(f"  Signals: {ingestion['total']} "
                          f"(github={ingestion['github']}, "
                          f"reddit={ingestion['reddit']}, devto={ingestion['devto']}, "
                          f"docs={ingestion['doc_changes']}, scheduled={ingestion['scheduled']})")

        try:
            sync_rewards_from_devto(self.db, self.config)
        except Exception:
            pass

        for i in range(max_actions):
            signal = claim_top_signal(self.db)
            if not signal:
                if console:
                    console.print("\n  No more pending signals.")
                break

            action = self._decide_action(signal)
            signal_type = signal.get("signal_type", "unknown")
            signal_title = signal.get("title", "")[:60]

            if console:
                console.print(
                    f"\n[bold yellow]DECIDE[/bold yellow] — Signal #{signal['id']}: "
                    f"[{signal_type}] {signal_title}"
                )
                console.print(f"  Score: {signal.get('score', 0):.3f} → Action: {action}")

            if action == "skip":
                mark_skipped(self.db, signal["id"], "engagement_drop — informational only")
                result["actions_skipped"] += 1
                continue

            if not self._firewall_check(action, console):
                mark_skipped(self.db, signal["id"], f"firewall denied: {action}")
                result["actions_skipped"] += 1
                continue

            if console:
                console.print(f"[bold green]ACT[/bold green] — Executing: {action}")

            if action in BROWSER_ENRICHABLE and signal.get("url"):
                self._enrich_signal_with_browser(signal, console)

            outcome = self._execute_action(action, signal, console)
            mark_acted(self.db, signal["id"], action, outcome)
            result["actions_taken"].append({
                "signal_id": signal["id"],
                "signal_type": signal_type,
                "action": action,
                "outcome": outcome,
            })

            if console:
                status = outcome.get("status", "unknown")
                console.print(f"  Result: {status}")

        if console:
            console.print("\n[bold magenta]LEARN[/bold magenta] — Recording cycle outcome...")

        self._record_lesson(result)

        # Post-cycle enforcement: prune stale memory (code, not prompt)
        try:
            from ..db import prune_memory
            prune_stats = prune_memory(self.db)
            if prune_stats["total_removed"] > 0 and console:
                console.print(f"  Memory pruned: {prune_stats['total_removed']} removed, "
                              f"{prune_stats['total_remaining']} remaining")
        except Exception:
            pass  # Pruning failure must not break the cycle

        stats = get_signal_stats(self.db)
        result["signal_stats"] = stats
        result["ended_at"] = now_iso()
        result["summary"] = (
            f"Ingested {ingestion['total']} signals, "
            f"took {len(result['actions_taken'])} actions, "
            f"skipped {result['actions_skipped']}. "
            f"Queue: {stats.get('pending', 0)} pending."
        )

        if console:
            console.print(f"\n[bold]Summary:[/bold] {result['summary']}")

        return result

    def _decide_action(self, signal: dict) -> str:
        signal_type = signal.get("signal_type", "")

        # For manual_goal (task issues): detect submit_form pattern before LLM
        if signal_type == "manual_goal":
            body = signal.get("body", "")
            import re as _re
            has_url = bool(_re.search(r'(?i)(?:url|target|form|link)\s*[:=]\s*https?://\S+', body))
            has_submit_keywords = bool(_re.search(r'(?i)\b(?:fill|submit|apply|application|form)\b', body))
            if has_url and has_submit_keywords:
                return "submit_form"

        action = ACTION_MAP.get(signal_type)

        if action is None:
            action = self._llm_decide(signal)

        if signal_type == "doc_gap":
            url = signal.get("url", "")
            if url:
                try:
                    existing = self.db.execute(
                        "SELECT COUNT(*) as cnt FROM content_pieces WHERE sources_json LIKE ?",
                        (f"%{url}%",),
                    ).fetchone()
                    if existing and existing["cnt"] > 0:
                        action = "update_content"
                except Exception:
                    pass

        if signal.get("confidence", 1.0) < 0.3:
            try:
                lessons = self.db.execute(
                    "SELECT insight FROM agent_memory WHERE lesson_type = 'strategy' "
                    "ORDER BY created_at DESC LIMIT 3"
                ).fetchall()
                if any("skip" in (row.get("insight", "") or "").lower() for row in lessons):
                    action = "skip"
            except Exception:
                pass

        return action or "write_content"

    def _llm_decide(self, signal: dict) -> str:
        if not self.config.has_anthropic:
            return "write_content"

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)

            valid_actions = list(set(ACTION_MAP.values()) - {"skip", None}) + ["submit_form"]
            response = client.messages.create(
                model=self.config.ai_model,
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Signal: type={signal.get('signal_type')}, "
                        f"title={signal.get('title', '')[:100]}, "
                        f"body={signal.get('body', '')[:200]}, "
                        f"source={signal.get('source')}\n\n"
                        f"Pick ONE action from: {valid_actions}\n"
                        f"submit_form = ONLY if body has an explicit URL, Name:, Email:, Location:, Visa:, and GDPR: fields for filling a web form. If any are missing, do NOT pick submit_form.\n"
                        f"write_content = write a blog post, tutorial, article, or application letter.\n"
                        f"draft_tweet = compose a tweet.\n"
                        f"generate_feedback = analyze docs for issues.\n"
                        f"browse_and_respond = read a URL and draft a response.\n"
                        f"Reply with just the action name, nothing else."
                    ),
                }],
            )
            chosen = response.content[0].text.strip().lower()
            if chosen in valid_actions:
                return chosen
        except Exception:
            pass

        return "write_content"

    def _enrich_signal_with_browser(self, signal: dict, console=None):
        url = signal.get("url", "")
        if not url or url.startswith("https://dev.to/api/"):
            return

        try:
            from .browser import fetch_page
            result = fetch_page(url, self.config)
            if result.get("status") == "ok":
                page_text = result.get("text", "")[:2000]
                signal["body"] = f"{signal.get('body', '')}\n\n--- Page Content ---\n{page_text}"
                if console:
                    console.print(f"  Browser: fetched {len(page_text)} chars from {url[:50]}")
        except Exception:
            pass

    def _firewall_check(self, action: str, console=None) -> bool:
        from .firewall import check as firewall_check

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0
        ).isoformat()

        context = {
            "dry_run": str(self.config.dry_run).lower(),
            "allow_writes": str(self.config.allow_writes).lower(),
        }

        try:
            for action_name in ("write_content", "draft_tweet", "draft_community_response",
                                "generate_feedback", "rebuild_site"):
                row = self.db.execute(
                    "SELECT COUNT(*) as cnt FROM signals "
                    "WHERE action_taken = ? AND acted_at >= ?",
                    (action_name, today_start),
                ).fetchone()
                context[f"{action_name}_today"] = row["cnt"] if row else 0
        except Exception:
            pass

        firewall_action = f"supervisor_{action}"
        verdict = firewall_check(firewall_action, context)

        if not verdict.allowed:
            if console:
                console.print(f"  [red]Firewall denied:[/red] {verdict.reason}")
            return False

        return True

    def _execute_action(self, action: str, signal: dict, console=None) -> dict:
        try:
            if action == "write_content":
                return self._act_write_content(signal, console)
            elif action == "draft_tweet":
                return self._act_draft_tweet(signal, console)
            elif action == "draft_community_response":
                return self._act_draft_response(signal, console)
            elif action == "generate_feedback":
                return self._act_generate_feedback(signal, console)
            elif action == "rebuild_site":
                return self._act_rebuild_site(console)
            elif action == "update_content":
                return self._act_write_content(signal, console)
            elif action == "browse_and_respond":
                return self._act_browse_and_respond(signal, console)
            elif action == "submit_form":
                return self._act_submit_form(signal, console)
            else:
                return {"status": "unknown_action", "action": action}
        except Exception as e:
            return {"status": "error", "error": str(e), "traceback": traceback.format_exc()[-500:]}

    def _act_write_content(self, signal: dict, console=None) -> dict:
        if not self.config.has_anthropic:
            return {"status": "skipped", "reason": "no anthropic key"}

        signal_title = signal.get("title", "")
        metadata = json.loads(signal.get("metadata_json", "{}") or "{}")

        # Task issues (manual_goal): use the task title + body directly
        is_task_issue = signal.get("signal_type") == "manual_goal"
        if is_task_issue and signal_title:
            category = "task_issue"
            topic = signal_title
        else:
            category = pull_arm(self.db)
            topic_suggestions = get_topic_for_category(category)
            topic = topic_suggestions[0] if topic_suggestions else "RevenueCat Developer Guide"

            if signal.get("signal_type") == "engagement_spike":
                slug = metadata.get("slug", "")
                if slug:
                    topic = f"Deep Dive: {signal_title.split(':')[-1].strip()}"

            if signal.get("signal_type") in ("pain_point", "new_issue"):
                topic = f"How to: {signal_title[:80]}"

        if console:
            console.print(f"  Category: {category}, Topic: {topic[:60]}")

        with start_run(self.db, "supervisor-write-content", {
            "topic": topic, "category": category, "signal_id": signal.get("id"),
        }, self.config) as ctx:
            try:
                from .core import AgenticCore

                core = AgenticCore(self.config, db_conn=self.db)
                if is_task_issue:
                    task_body = signal.get("body", "")[:2000]
                    goal = f"{topic}\n\nTask details:\n{task_body}" if task_body else topic
                    max_turns = 6
                else:
                    goal = f"Write a tutorial about: {topic}"
                    max_turns = 12
                result = core.run_cycle(
                    goal=goal,
                    max_turns=max_turns,
                    console=console,
                )

                log_tool_call(ctx, "agentic_core.run_cycle", f"topic={topic[:50]}", f"turns={result.get('turns', 0)}")
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    artifact_type="content_piece",
                    additional={"category": category, "signal_type": signal.get("signal_type")},
                ), verification=None, success=True)

                return {
                    "status": "success",
                    "category": category,
                    "topic": topic,
                    "turns": result.get("turns", 0),
                    "actions": len(result.get("actions_taken", [])),
                }
            except Exception as e:
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    additional={"error": str(e)},
                ), verification=None, success=False)
                return {"status": "error", "error": str(e)}

    def _act_draft_tweet(self, signal: dict, console=None) -> dict:
        if not self.config.has_anthropic:
            return {"status": "skipped", "reason": "no anthropic key"}

        with start_run(self.db, "supervisor-tweet", {
            "signal_id": signal.get("id"),
        }, self.config) as ctx:
            try:
                from ..social.twitter import TwitterClient
                from ..knowledge.search import build_index

                index = build_index(self.config.docs_cache_dir, self.db)
                client = TwitterClient(self.config)
                result = client.autonomous_post(index)

                log_tool_call(ctx, "twitter.autonomous_post", "", json.dumps(result)[:200])
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    artifact_type="tweet",
                    additional=result,
                ), verification=None, success=result.get("status") != "error")

                return result
            except Exception as e:
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    additional={"error": str(e)},
                ), verification=None, success=False)
                return {"status": "error", "error": str(e)}

    def _act_draft_response(self, signal: dict, console=None) -> dict:
        source = signal.get("source", "")
        metadata = json.loads(signal.get("metadata_json", "{}") or "{}")

        with start_run(self.db, "supervisor-community-response", {
            "source": source, "signal_id": signal.get("id"),
        }, self.config) as ctx:
            try:
                from ..knowledge.search import build_index, search as search_docs

                index = build_index(self.config.docs_cache_dir, self.db)
                query = f"{signal.get('title', '')} {signal.get('body', '')[:200]}"
                results = search_docs(query, index, self.config.docs_cache_dir, top_k=5)

                from ..community.responder import draft_response
                response_text = draft_response(query, results, self.config)

                insert_row(self.db, "community_interactions", {
                    "channel": "github" if source == "github" else "reddit",
                    "thread_url": signal.get("url", ""),
                    "counterpart": metadata.get("user", ""),
                    "intent": "answer_question",
                    "question": signal.get("title", ""),
                    "draft_response": response_text,
                    "status": "draft",
                    "created_at": now_iso(),
                })

                log_tool_call(ctx, "draft_response", f"source={source}", f"{len(response_text)} chars")
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    artifact_type="community_response",
                    word_count=len(response_text.split()),
                ), verification=None, success=True)

                return {
                    "status": "drafted",
                    "source": source,
                    "response_length": len(response_text),
                    "sources_used": len(results),
                }
            except Exception as e:
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    additional={"error": str(e)},
                ), verification=None, success=False)
                return {"status": "error", "error": str(e)}

    def _act_generate_feedback(self, signal: dict, console=None) -> dict:
        if not self.config.has_anthropic:
            return {"status": "skipped", "reason": "no anthropic key"}

        with start_run(self.db, "supervisor-feedback", {
            "signal_id": signal.get("id"),
        }, self.config) as ctx:
            try:
                from ..knowledge.search import build_index
                from ..feedback.collector import generate_feedback_from_docs

                index = build_index(self.config.docs_cache_dir, self.db)
                feedback_items = generate_feedback_from_docs(index, self.config, self.db, ctx, count=2)

                log_tool_call(ctx, "generate_feedback", "count=2", f"{len(feedback_items)} items")
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    artifact_type="product_feedback",
                    additional={"count": len(feedback_items)},
                ), verification=None, success=True)

                return {"status": "success", "feedback_count": len(feedback_items)}
            except Exception as e:
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    additional={"error": str(e)},
                ), verification=None, success=False)
                return {"status": "error", "error": str(e)}

    def _act_rebuild_site(self, console=None) -> dict:
        with start_run(self.db, "supervisor-build-site", {}, self.config) as ctx:
            try:
                from ..site.generator import build_site
                build_site(self.db, self.config)

                log_tool_call(ctx, "build_site", "", "site rebuilt")
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    artifact_type="site_build",
                ), verification=None, success=True)

                return {"status": "success"}
            except Exception as e:
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    additional={"error": str(e)},
                ), verification=None, success=False)
                return {"status": "error", "error": str(e)}

    def _act_submit_form(self, signal: dict, console=None) -> dict:
        """Use Playwright MCP to navigate to a URL, read the form, fill it, submit."""
        if not self.config.has_anthropic:
            return {"status": "skipped", "reason": "no anthropic key"}
        if self.config.dry_run:
            return {"status": "skipped", "reason": "dry_run blocks form submission"}

        body = signal.get("body", "")
        import re
        # Extract target URL from issue body.
        # Prefer explicit "URL: ..." or "Target: ..." field to avoid picking the wrong
        # link in multi-URL issues. Fall back to first URL if no explicit field found.
        explicit_url = re.search(r'(?i)(?:url|target|form|link)\s*[:=]\s*(https?://\S+)', body)
        if explicit_url:
            url = explicit_url.group(1).rstrip(")")
        else:
            urls = re.findall(r'https?://\S+', body)
            url = urls[0] if urls else ""
        if not url:
            return {"status": "error", "error": "no target URL found in issue body"}

        # Validate operator provided required personal/legal fields.
        # Identity fields
        has_email = bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', body))
        has_name = bool(re.search(r'(?i)(?:name|operator)[^:=\n]*[:=]\s*\S+', body))
        # Legal/consent fields — required for form submissions involving personal data
        has_location = bool(re.search(r'(?i)(?:location|city|country|address)\s*[:=]\s*\S+', body))
        has_visa = bool(re.search(r'(?i)(?:visa|work.?auth|authorization|right.?to.?work|citizenship)\s*[:=]\s*\S+', body))
        has_gdpr = bool(re.search(r'(?i)(?:gdpr|consent|data.?processing|privacy)\s*[:=]\s*(?:yes|true|agree|accept)', body))
        missing = []
        if not has_name:
            missing.append("name (expected 'Name: ...' line)")
        if not has_email:
            missing.append("email (expected an email address)")
        if not has_location:
            missing.append("location (expected 'Location: ...' line)")
        if not has_visa:
            missing.append("visa/work authorization (expected 'Visa: ...' or 'Work Authorization: ...' line)")
        if not has_gdpr:
            missing.append("GDPR/data consent (expected 'GDPR: yes' or 'Consent: agree' line)")
        if missing:
            return {"status": "error", "error": f"issue body missing: {', '.join(missing)}"}

        with start_run(self.db, "supervisor-submit-form", {
            "url": url, "signal_id": signal.get("id"),
        }, self.config) as ctx:
            try:
                from .browser import PlaywrightMCPBrowser, _run_async

                async def _do_form():
                    browser = PlaywrightMCPBrowser(self.config)
                    await browser.connect()
                    try:
                        # Build agent self-knowledge context
                        site_url = ""
                        repo_url = ""
                        if self.config.github_repo:
                            owner, repo = self.config.github_repo.split("/", 1)
                            site_url = f"https://{owner}.github.io/{repo}"
                            repo_url = f"https://github.com/{self.config.github_repo}"

                        agent_ctx = "Agent self-knowledge:\n"
                        agent_ctx += f"- Name: {self.config.agent_name}\n"
                        agent_ctx += f"- Application letter: {site_url}/apply\n"
                        agent_ctx += f"- GitHub: {repo_url}\n"
                        agent_ctx += f"- Live site: {site_url}\n"
                        agent_ctx += "- Twitter/X: https://x.com/RevenueCat_agad (@RevenueCat_agad)\n"
                        agent_ctx += f"- Demo pages: {site_url}/content , {site_url}/experiments , {site_url}/feedback , {site_url}/ledger\n"
                        try:
                            from ..db import query_rows
                            cp = query_rows(self.db, "content_pieces")
                            fb = query_rows(self.db, "product_feedback")
                            ex = query_rows(self.db, "growth_experiments")
                            agent_ctx += f"- Produced: {len(cp)} content, {len(fb)} feedback, {len(ex)} experiments\n"
                        except Exception:
                            pass

                        import anthropic
                        client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)

                        system_prompt = (
                            "You are an autonomous agent filling out a web form using browser tools. "
                            "You operate in a loop: observe the page, decide your next action, execute it, "
                            "then observe the result. You have these tools:\n"
                            "- browser_click: click an element. Args: {\"element\": \"description\", \"ref\": \"refN\"}\n"
                            "- browser_type: type text into a field. Args: {\"element\": \"description\", \"ref\": \"refN\", \"text\": \"value\"}\n"
                            "- browser_select_option: select a dropdown option. Args: {\"element\": \"description\", \"ref\": \"refN\", \"values\": [\"option\"]}\n"
                            "- browser_press_key: press a keyboard key. Args: {\"key\": \"PageDown\"} or {\"key\": \"End\"} or {\"key\": \"Tab\"}\n"
                            "- browser_snapshot: get the current page accessibility snapshot. Args: {} (no args needed)\n"
                            "\nRules:\n"
                            "- Do ONE action at a time, then observe the result.\n"
                            "- Personal fields (name, email, location, visa) come from operator details.\n"
                            "- Questions about agent capabilities, links, portfolio — use agent self-knowledge.\n"
                            "- When you see a file upload field for resume/CV, skip it.\n"
                            "- IMPORTANT: You will receive both accessibility tree text AND screenshots. "
                            "When the accessibility tree is truncated, use the SCREENSHOT to visually identify elements.\n"
                            "- The privacy/GDPR consent field is usually a DROPDOWN/SELECT (not a checkbox). "
                            "Use browser_select_option or browser_click to select the correct option. "
                            "If the operator says 'I am not located in the UK', select 'I am not located in the EEA/UK' or similar.\n"
                            "- If you can see an element in the screenshot but not in the accessibility tree, try browser_press_key with 'Tab' "
                            "to navigate to it, then browser_press_key with 'Enter' or 'Space' to activate it.\n"
                            "- Do NOT press Space on form fields you already filled — it will clear them.\n"
                            "- When done filling all fields, click the submit button.\n"
                            "- Only say DONE after you have attempted a real submit click.\n"
                            "- DONE is invalid if you have not attempted submit.\n"
                            "\nRespond with a JSON object: {\"tool\": \"...\", \"args\": {...}, \"reasoning\": \"...\"}\n"
                            "Or {\"done\": true, \"reasoning\": \"...\"} when the form is submitted."
                        )

                        # Navigate and get initial state
                        nav_result = await browser.navigate(url)
                        if nav_result.get("status") != "ok":
                            return {
                                "status": "error",
                                "error": f"initial navigation failed: {nav_result.get('status', 'unknown')}",
                                "url": url,
                                "details": nav_result,
                            }
                        snapshot = await browser.snapshot()
                        page_content = snapshot.get("content", "")

                        messages = [{
                            "role": "user",
                            "content": (
                                f"Task: {signal.get('title', '')}\n\n"
                                f"Operator details:\n{body[:4000]}\n\n"
                                f"{agent_ctx}\n\n"
                                f"Current page state:\n{page_content[:20000]}\n\n"
                                f"Observe this form and decide your first action."
                            ),
                        }]

                        max_steps = 25
                        allowed_tools = {"browser_click", "browser_type", "browser_select_option", "browser_press_key", "browser_snapshot", "browser_screenshot"}
                        actions_taken = []
                        submit_attempted = False
                        done_received = False
                        action_errors = 0
                        typed_fields = 0
                        consecutive_errors = 0
                        last_page = page_content
                        import json as _json

                        for step in range(max_steps):
                            resp = client.messages.create(
                                model=self.config.ai_model,
                                max_tokens=1000,
                                system=system_prompt,
                                messages=messages,
                            )
                            reply = resp.content[0].text.strip()

                            # Parse the response
                            try:
                                if reply.startswith("```"):
                                    reply = reply.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                                action_data = _json.loads(reply)
                            except (_json.JSONDecodeError, IndexError):
                                # LLM returned non-JSON — check if it said DONE
                                if "DONE" in reply.upper() or "done" in reply:
                                    done_received = True
                                    break
                                messages.append({"role": "assistant", "content": reply})
                                messages.append({"role": "user", "content": "Respond with valid JSON. One action at a time."})
                                continue

                            # Check if done
                            if action_data.get("done"):
                                done_received = True
                                if console:
                                    console.print(f"  Step {step + 1}: DONE — {action_data.get('reasoning', '')[:80]}")
                                break

                            tool = action_data.get("tool", "")
                            args = action_data.get("args", {}) or {}
                            reasoning = action_data.get("reasoning", "")

                            if tool not in allowed_tools:
                                actions_taken.append({
                                    "step": step + 1,
                                    "tool": tool,
                                    "element": args.get("element", ""),
                                    "status": "error",
                                    "error": "invalid_tool",
                                })
                                action_errors += 1
                                consecutive_errors += 1
                                messages.append({"role": "assistant", "content": reply})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        f"Tool '{tool}' is invalid. Use one of: {sorted(allowed_tools)}. "
                                        "Retry with valid JSON for one action."
                                    ),
                                })
                                if consecutive_errors >= 5:
                                    break
                                continue

                            if console:
                                console.print(f"  Step {step + 1}: {tool}({args.get('element', '')[:40]}) — {reasoning[:60]}")

                            element_text = str(args.get("element", "")).lower()
                            reasoning_text = str(reasoning).lower()

                            # Execute the action
                            try:
                                result = await browser.call_tool(tool, args)
                                result_status = result.get("status", "ok")
                                if result_status != "ok":
                                    action_errors += 1
                                    consecutive_errors += 1
                                    action_result = f"Action failed. Result: {_json.dumps(result)[:500]}"
                                    actions_taken.append({
                                        "step": step + 1, "tool": tool, "element": args.get("element", ""),
                                        "status": "error", "error": result_status,
                                    })
                                else:
                                    consecutive_errors = 0
                                    action_result = f"Action executed. Result: {_json.dumps(result)[:500]}"
                                    actions_taken.append({
                                        "step": step + 1, "tool": tool, "element": args.get("element", ""),
                                        "status": "ok",
                                    })
                                    if tool == "browser_type":
                                        typed_fields += 1
                                    # Mark submit after click or key press on submit-related elements
                                    _submit_kws = ("submit", "apply", "send application", "complete application")
                                    if tool == "browser_click" and any(
                                        kw in element_text or kw in reasoning_text
                                        for kw in _submit_kws
                                    ):
                                        submit_attempted = True
                                    # Also detect submit via keyboard (Tab to submit + Enter/Space)
                                    if tool == "browser_press_key" and any(
                                        kw in reasoning_text for kw in _submit_kws
                                    ):
                                        key_pressed = str(args.get("key", "")).lower()
                                        if key_pressed in ("enter", "space", " "):
                                            submit_attempted = True
                            except Exception as e:
                                action_errors += 1
                                consecutive_errors += 1
                                action_result = f"Action failed: {str(e)[:200]}"
                                actions_taken.append({"step": step + 1, "tool": tool, "element": args.get("element", ""), "status": "error", "error": str(e)[:100]})

                            # Observe: get fresh page state after action
                            try:
                                snapshot = await browser.snapshot()
                                new_page = snapshot.get("content", "")
                                last_page = new_page
                            except Exception:
                                new_page = "(snapshot failed)"

                            messages.append({"role": "assistant", "content": reply})

                            # Always use screenshot for visual grounding
                            use_screenshot = True
                            screenshot_b64 = None
                            if use_screenshot:
                                try:
                                    ss_result = await browser.call_tool("browser_screenshot")
                                    if ss_result.get("images"):
                                        screenshot_b64 = ss_result["images"][0]["data"]
                                except Exception:
                                    pass

                            if screenshot_b64:
                                import base64 as _b64
                                messages.append({
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": f"{action_result}\n\nAccessibility tree (may be truncated):\n{new_page[:8000]}\n\nScreenshot of current page below. Use it to identify elements not visible in the accessibility tree. Decide your next action."},
                                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}},
                                    ],
                                })
                            else:
                                messages.append({
                                    "role": "user",
                                    "content": f"{action_result}\n\nCurrent page state:\n{new_page[:20000]}\n\nDecide your next action."
                                })

                            if consecutive_errors >= 5:
                                break

                        confirm_keywords = (
                            "thank you", "application submitted", "submission received",
                            "we have received your application", "application has been submitted",
                        )
                        submission_confirmed = any(k in (last_page or "").lower() for k in confirm_keywords)

                        if typed_fields == 0:
                            return {
                                "status": "error",
                                "error": "form fill failed: no fields were typed",
                                "actions_taken": len(actions_taken),
                                "steps": actions_taken,
                                "url": url,
                            }

                        if not submit_attempted:
                            return {
                                "status": "error",
                                "error": "form was not submitted: no submit click attempted",
                                "actions_taken": len(actions_taken),
                                "steps": actions_taken,
                                "url": url,
                            }

                        if not done_received and not submission_confirmed:
                            return {
                                "status": "error",
                                "error": "form loop ended before completion signal",
                                "actions_taken": len(actions_taken),
                                "steps": actions_taken,
                                "url": url,
                            }

                        return {
                            "status": "submitted",
                            "actions_taken": len(actions_taken),
                            "steps": actions_taken,
                            "url": url,
                            "submit_attempted": submit_attempted,
                            "done_received": done_received,
                            "submission_confirmed": submission_confirmed,
                            "action_errors": action_errors,
                            "typed_fields": typed_fields,
                        }
                    finally:
                        await browser.disconnect()

                result = _run_async(_do_form())

                log_tool_call(ctx, "submit_form", f"url={url[:60]}", json.dumps(result)[:200])
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    artifact_type="form_submission",
                    additional=result,
                ), verification=None, success=result.get("status") == "submitted")

                return result
            except Exception as e:
                finalize_run(ctx, self.config, self.db, LedgerOutputs(
                    additional={"error": str(e)},
                ), verification=None, success=False)
                return {"status": "error", "error": str(e)}

    def _act_browse_and_respond(self, signal: dict, console=None) -> dict:
        url = signal.get("url", "")
        if not url:
            return self._act_draft_response(signal, console)

        try:
            from .browser import fetch_page
            page_result = fetch_page(url, self.config)
            if page_result.get("status") == "ok":
                signal["body"] = page_result.get("text", "")[:3000]
        except Exception:
            pass

        return self._act_draft_response(signal, console)

    def _record_lesson(self, cycle_result: dict):
        actions = cycle_result.get("actions_taken", [])
        if not actions:
            return

        action_summary = ", ".join(
            f"{a['action']}({a.get('outcome', {}).get('status', '?')})"
            for a in actions
        )

        try:
            insert_row(self.db, "agent_memory", {
                "cycle_id": f"supervisor_{cycle_result.get('started_at', '')}",
                "lesson_type": "strategy",
                "key": f"supervisor_cycle_{len(actions)}_actions",
                "insight": f"Supervisor cycle: {action_summary}",
                "evidence": json.dumps({
                    "signals_ingested": cycle_result.get("signals_ingested", {}),
                    "actions": [
                        {"signal_type": a.get("signal_type"), "action": a.get("action"),
                         "status": a.get("outcome", {}).get("status")}
                        for a in actions
                    ],
                }),
                "confidence": 0.7,
                "created_at": now_iso(),
            })
        except Exception:
            pass
