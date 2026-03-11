"""Agentic core: the autonomous brain of the advocate system.

This is what makes the system genuinely agentic. Instead of dumb pipelines
(outline → write) or random schedulers (pick topic → execute), the core agent:

1. OBSERVES — queries DB, scans community signals, checks what's been done
2. REASONS — decides what action would have the most impact right now
3. ACTS — executes through multi-turn tool use with self-directed research
4. EVALUATES — critiques its own output before finalizing
5. ADAPTS — adjusts strategy based on what worked and what didn't

The agent loop runs until the task is complete or max turns are reached.
Every tool call and decision is logged to the tamper-evident ledger.
"""
import json
import time
import traceback

from ..config import Config
from ..db import init_db_from_config, query_rows, count_rows, now_iso


# The tools the agent can use — each maps to real system capabilities
CORE_AGENT_TOOLS = [
    {
        "name": "analyze_state",
        "description": "Analyze the current state of the advocate system: how many content pieces exist, what topics have been covered, what experiments are running, recent community signals, etc. Use this FIRST to understand what's been done and what needs attention.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "search_docs",
        "description": "Search RevenueCat's ingested documentation. Returns ranked results with snippets and source URLs. Use this to find specific technical information for content, responses, or research.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "scan_community",
        "description": "Scan GitHub issues and Reddit for what developers are struggling with RIGHT NOW. Returns recent issues and posts across RevenueCat repos and developer subreddits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Look back N hours", "default": 72},
            },
            "required": [],
        },
    },
    {
        "name": "write_content",
        "description": "Write a full technical content piece (tutorial, case study, or agent playbook). The agent will research the topic using docs, create an outline, write the draft with citations, and self-evaluate quality. Returns the content piece details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The topic to write about"},
                "content_type": {"type": "string", "enum": ["tutorial", "case_study", "agent_playbook"], "description": "Type of content"},
                "guidance": {"type": "string", "description": "Optional: specific angle, audience, or points to emphasize"},
            },
            "required": ["topic", "content_type"],
        },
    },
    {
        "name": "draft_tweet",
        "description": "Draft a tweet or thread using the agentic tweet writer. The tweet agent will research using docs/GitHub/Reddit, then compose. Returns the drafted tweet text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What to tweet about"},
                "thread": {"type": "boolean", "description": "If true, draft a thread instead of single tweet", "default": False},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "post_tweet",
        "description": "Autonomously research, draft, and POST a tweet or thread to @RevenueCat_agad. The social media agent handles everything end-to-end: research → compose → post.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What to tweet about"},
                "thread": {"type": "boolean", "description": "If true, post a thread", "default": False},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "generate_feedback",
        "description": "Analyze documentation and generate structured product feedback with repro steps, expected vs actual behavior, and proposed fixes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus_area": {"type": "string", "description": "Optional: focus on a specific area (sdk, api, docs, charts, mcp, paywalls, etc.)"},
                "count": {"type": "integer", "description": "Number of feedback items", "default": 2},
            },
            "required": [],
        },
    },
    {
        "name": "draft_community_response",
        "description": "Draft a response to a specific community question (GitHub issue, Reddit post, etc.) grounded in documentation with citations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question or issue to respond to"},
                "context": {"type": "string", "description": "Additional context (repo name, post URL, etc.)"},
                "channel": {"type": "string", "enum": ["github", "reddit", "stackoverflow", "twitter", "other"]},
            },
            "required": ["question", "channel"],
        },
    },
    {
        "name": "evaluate_output",
        "description": "Self-evaluate a piece of content or response. Check: Is it grounded in docs? Does it have citations? Is it useful to developers? Would a real developer find value in this? Be brutally honest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The content to evaluate"},
                "content_type": {"type": "string", "description": "What kind of content (tweet, article, response, feedback)"},
                "criteria": {"type": "string", "description": "Specific evaluation criteria"},
            },
            "required": ["content", "content_type"],
        },
    },
    {
        "name": "decide_next_action",
        "description": "Record your reasoning about what to do next. This is a structured thinking tool — it logs your observations and decision but does not enforce any control flow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "observations": {"type": "string", "description": "What you've observed about the current state"},
                "options": {"type": "array", "items": {"type": "string"}, "description": "Possible actions to take"},
                "decision": {"type": "string", "description": "Your chosen action and why"},
            },
            "required": ["observations", "options", "decision"],
        },
    },
    {
        "name": "build_site",
        "description": "Rebuild the static site from all DB content and artifacts.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "publish_to_devto",
        "description": "Publish all verified content pieces to Dev.to. Returns what was published with URLs. Use this after writing content to get it in front of developers immediately.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "sync_devto_stats",
        "description": "Pull engagement stats (views, reactions, comments) from Dev.to for all published articles. Use this to see what content is performing well.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "record_lesson",
        "description": "Record a lesson learned for future cycles. This builds persistent memory that feeds into future decisions. ALWAYS record lessons at the end of a cycle.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lesson_type": {"type": "string", "enum": ["content_perf", "topic_signal", "channel_insight", "strategy", "failure"], "description": "Category of lesson"},
                "key": {"type": "string", "description": "Short label, e.g. 'vibe-coding-articles' or 'devto-tutorial-format'"},
                "insight": {"type": "string", "description": "What you learned — be specific and actionable"},
                "evidence": {"type": "string", "description": "Data backing this lesson (stats, observations, comparisons)"},
                "confidence": {"type": "number", "description": "How confident 0.0-1.0 (use 0.3 for hunches, 0.7 for observed patterns, 0.9 for measured results)"},
            },
            "required": ["lesson_type", "key", "insight"],
        },
    },
    {
        "name": "complete",
        "description": "Signal that you've completed the current task cycle. Summarize what was accomplished. IMPORTANT: always record_lesson BEFORE completing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was accomplished in this cycle"},
                "next_priorities": {"type": "array", "items": {"type": "string"}, "description": "Suggested priorities for the next cycle"},
            },
            "required": ["summary"],
        },
    },
]


CORE_AGENT_SYSTEM = """\
You are a persistent autonomous Developer Advocate operator for RevenueCat. You are not \
a one-shot content generator — you are a living agent that remembers what it tried, \
measures what worked, and gets smarter every cycle.

YOUR LOOP (every cycle):
1. OBSERVE — analyze_state shows your full history: content published, Dev.to engagement \
stats, past lessons learned, community signals. sync_devto_stats first to get fresh numbers.
2. REASON — What content performed well? What topics are trending? What hasn't been tried? \
Use decide_next_action to log your thinking. Check your LESSONS LEARNED section carefully.
3. ACT — Write content, generate feedback, draft tweets, scan community. Pick actions \
based on data, not random topics.
4. PUBLISH — Use publish_to_devto to push verified content live immediately.
5. LEARN — Use record_lesson to write back what you tried and why. This memory persists \
across cycles. Future-you will read it. Be specific and actionable.

TOPIC SELECTION (data-driven):
- analyze_state shows existing article titles — NEVER repeat a topic.
- Dev.to stats show which articles get views/reactions — double down on what works.
- Community signals show trending pain points — write about real problems.
- Past lessons tell you what formats/angles resonated — use them.
- search_docs reveals documentation gaps — that's where the best content comes from.

QUALITY STANDARDS:
- Every factual claim must be citation-backed from docs
- Content must solve a real developer problem, not list features
- Feedback must be actionable with repro steps

EFFICIENCY RULES:
- Each cycle MUST produce at least one long-form article via write_content on a NEW topic.
- After writing, publish_to_devto to get it live.
- Draft at most 1 community response per cycle.
- ALWAYS record_lesson before calling complete — even if the lesson is "this didn't work."

You are building a track record. Every cycle adds to it. Act accordingly.\
"""


class AgenticCore:
    """The autonomous brain — runs the observe-reason-act-evaluate loop."""

    def __init__(self, config: Config, db_conn=None, search_index=None):
        self.config = config
        self.db = db_conn or init_db_from_config(config)
        self.search_index = search_index
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)

    def _ensure_search_index(self):
        if self.search_index is None:
            from ..knowledge.search import build_index
            self.search_index = build_index(self.config.docs_cache_dir, self.db)

    def run_cycle(self, goal: str = None, max_turns: int = 15, console=None) -> dict:
        """Run one autonomous cycle. The agent decides what to do.

        Args:
            goal: Optional high-level goal. If None, agent decides autonomously.
            max_turns: Maximum tool-use turns before forcing completion.
            console: Optional Rich console for output.

        Returns:
            Dict with summary, actions_taken, and outputs.
        """
        self._ensure_client()
        self._ensure_search_index()

        if goal:
            user_msg = f"Goal for this cycle: {goal}\n\nStart by analyzing the current state, then decide and execute the best approach."
        else:
            user_msg = (
                "Run an autonomous advocacy cycle. Start by analyzing the current state "
                "and community signals, then decide what action would have the most impact "
                "right now. Execute it, evaluate the result, and complete."
            )

        messages = [{"role": "user", "content": user_msg}]
        actions_taken = []
        result_summary = None
        turn = 0

        from ..ledger import start_run, finalize_run, log_tool_call
        from ..models import LedgerOutputs

        with start_run(self.db, "agent-cycle", {"goal": goal or "autonomous"}, self.config) as ledger_ctx:
            for turn in range(max_turns):
                time.sleep(0.3)

                try:
                    response = self._client.messages.create(
                        model=self.config.ai_model,
                        max_tokens=4096,
                        system=CORE_AGENT_SYSTEM,
                        tools=CORE_AGENT_TOOLS,
                        messages=messages,
                    )
                except Exception as e:
                    if console:
                        console.print(f"  [red]API error: {e}[/red]")
                    log_tool_call(ledger_ctx, "api_error", "", f"{type(e).__name__}: {e}")
                    result_summary = f"Failed: {e}"
                    break

                # Handle end_turn (no more tool calls)
                if response.stop_reason == "end_turn":
                    for block in response.content:
                        if hasattr(block, "text") and block.text:
                            if console:
                                console.print(f"  [dim]{block.text[:200]}[/dim]")
                            if not result_summary and len(block.text) > 20:
                                result_summary = block.text
                    break

                # Process tool calls
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input

                        if console:
                            input_preview = json.dumps(tool_input)[:100]
                            console.print(f"  [cyan][agent] {tool_name}[/cyan]({input_preview})")

                        log_tool_call(ledger_ctx, f"agent.{tool_name}",
                                      json.dumps(tool_input)[:200], "")

                        # Execute the tool
                        result = self._handle_tool(tool_name, tool_input, ledger_ctx, console)
                        actions_taken.append({"tool": tool_name, "input": tool_input})

                        if tool_name == "complete":
                            result_summary = tool_input.get("summary", "Cycle complete")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "Cycle completed.",
                            })
                        else:
                            # Truncate long results for context window
                            if len(result) > 6000:
                                result = result[:6000] + "\n... (truncated)"
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                if result_summary:
                    break

            # ── Post-cycle enforcement (code, not prompt) ──────────────
            # These run regardless of what the agent chose to do.
            post_cycle_notes = []

            # 1. Always sync Dev.to stats if key is configured
            if self.config.has_devto:
                try:
                    stats_result = self._tool_sync_devto_stats()
                    log_tool_call(ledger_ctx, "post_cycle.sync_devto_stats", "", stats_result[:200])
                    post_cycle_notes.append("devto_stats_synced")
                except Exception as e:
                    post_cycle_notes.append(f"devto_stats_failed: {e}")

            # 2. Warn if no lessons were recorded this cycle
            tools_used = [a["tool"] for a in actions_taken]
            lesson_recorded = "record_lesson" in tools_used
            if not lesson_recorded:
                post_cycle_notes.append("WARNING: no lesson recorded this cycle")
                if console:
                    console.print("  [yellow]Post-cycle: agent did not record any lessons[/yellow]")

            finalize_run(ledger_ctx, self.config, self.db,
                         outputs=LedgerOutputs(
                             artifact_type="agent_cycle",
                             additional={
                                 "actions": len(actions_taken),
                                 "turns": turn + 1,
                                 "summary": (result_summary or "")[:500],
                                 "post_cycle": post_cycle_notes,
                                 "lesson_recorded": lesson_recorded,
                             },
                         ),
                         verification=None)

        return {
            "summary": result_summary or "Agent cycle completed",
            "actions_taken": actions_taken,
            "turns": turn + 1,
            "lesson_recorded": lesson_recorded,
        }

    def _handle_tool(self, name: str, inp: dict, ledger_ctx, console=None) -> str:
        """Execute a tool call from the agent."""
        try:
            if name == "analyze_state":
                return self._tool_analyze_state()
            elif name == "search_docs":
                return self._tool_search_docs(inp)
            elif name == "scan_community":
                return self._tool_scan_community(inp)
            elif name == "write_content":
                return self._tool_write_content(inp, ledger_ctx, console)
            elif name == "draft_tweet":
                return self._tool_draft_tweet(inp)
            elif name == "post_tweet":
                return self._tool_post_tweet(inp)
            elif name == "generate_feedback":
                return self._tool_generate_feedback(inp, ledger_ctx)
            elif name == "draft_community_response":
                return self._tool_draft_response(inp, ledger_ctx)
            elif name == "evaluate_output":
                return self._tool_evaluate(inp)
            elif name == "decide_next_action":
                return self._tool_decide(inp)
            elif name == "build_site":
                return self._tool_build_site()
            elif name == "publish_to_devto":
                return self._tool_publish_devto()
            elif name == "sync_devto_stats":
                return self._tool_sync_devto_stats()
            elif name == "record_lesson":
                return self._tool_record_lesson(inp, ledger_ctx)
            elif name == "complete":
                return inp.get("summary", "Complete")
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            return f"Error in {name}: {e}\n{traceback.format_exc()[-300:]}"

    def _tool_analyze_state(self) -> str:
        """Return comprehensive system state for the agent to reason about."""
        content = query_rows(self.db, "content_pieces", order_by="created_at DESC", limit=10)
        experiments = query_rows(self.db, "growth_experiments", order_by="created_at DESC", limit=5)
        feedback = query_rows(self.db, "product_feedback", order_by="created_at DESC", limit=5)
        interactions = query_rows(self.db, "community_interactions", order_by="created_at DESC", limit=10)
        runs = query_rows(self.db, "run_log", order_by="sequence DESC", limit=5)

        lines = ["=== SYSTEM STATE ===\n"]

        # Content summary
        lines.append(f"CONTENT: {count_rows(self.db, 'content_pieces')} total pieces")
        if content:
            lines.append("EXISTING ARTICLES (DO NOT write about these topics again):")
            all_content = query_rows(self.db, "content_pieces", order_by="created_at DESC", limit=50)
            non_apply = [c for c in all_content if c.get("slug") != "application-letter"]
            for c in non_apply:
                lines.append(f"  - {c['title']}")
            lines.append("\nYou MUST pick a topic NOT on this list. Think about what's missing.")
        else:
            lines.append("  No content yet — this is a priority!")

        # Experiments
        lines.append(f"\nEXPERIMENTS: {count_rows(self.db, 'growth_experiments')} total")
        for e in experiments[:3]:
            lines.append(f"  - {e['name']}: {e['hypothesis'][:80]}")

        # Feedback
        lines.append(f"\nFEEDBACK: {count_rows(self.db, 'product_feedback')} items filed")
        for f in feedback[:3]:
            lines.append(f"  - [{f['severity']}] {f['title']} ({f['area']})")

        # Community
        lines.append(f"\nCOMMUNITY: {count_rows(self.db, 'community_interactions')} interactions")
        if interactions:
            channel_counts = {}
            for ix in interactions:
                ch = ix.get("channel", "unknown")
                channel_counts[ch] = channel_counts.get(ch, 0) + 1
            lines.append(f"  By channel: {channel_counts}")
            for ix in interactions[:3]:
                q = ix.get("question", "")[:60]
                lines.append(f"  - [{ix.get('channel')}] {q}")

        # Ledger
        lines.append(f"\nLEDGER: {count_rows(self.db, 'run_log')} entries")
        if runs:
            lines.append(f"  Last run: {runs[0].get('command')} at {runs[0].get('started_at')}")

        # Dev.to performance (what's working)
        published = [c for c in (query_rows(self.db, "content_pieces", order_by="devto_views DESC", limit=20))
                     if c.get("devto_article_id")]
        if published:
            lines.append("\nDEV.TO PERFORMANCE (published articles, sorted by views):")
            for p in published:
                lines.append(f"  - {p['title'][:60]}: {p.get('devto_views', 0)} views, "
                             f"{p.get('devto_reactions', 0)} reactions, {p.get('devto_comments', 0)} comments")
                if p.get("devto_url"):
                    lines.append(f"    URL: {p['devto_url']}")
        else:
            lines.append("\nDEV.TO: No articles published yet. Use publish_to_devto after writing.")

        # Lessons learned (persistent memory from past cycles)
        lessons = query_rows(self.db, "agent_memory", order_by="created_at DESC", limit=15)
        if lessons:
            lines.append("\nLESSONS LEARNED (from past cycles — use these to make better decisions):")
            for lesson in lessons:
                conf = lesson.get("confidence", 0.5)
                lines.append(f"  [{lesson['lesson_type']}] {lesson['key']}: {lesson['insight']}")
                if lesson.get("evidence"):
                    lines.append(f"    Evidence: {lesson['evidence'][:100]}")
                lines.append(f"    Confidence: {conf:.1f} | Recorded: {lesson['created_at'][:10]}")
        else:
            lines.append("\nLESSONS: No lessons recorded yet. Start recording what works and what doesn't.")

        # Doc index
        lines.append(f"\nDOCS INDEX: {self.search_index.doc_count if self.search_index else 0} documents indexed")

        return "\n".join(lines)

    def _tool_search_docs(self, inp: dict) -> str:
        from ..knowledge.search import search as search_docs
        results = search_docs(inp["query"], self.search_index, self.config.docs_cache_dir, top_k=5)
        if not results:
            return "No results found."
        out = []
        for r in results:
            out.append(f"**{r.title}** (score: {r.score:.2f})\nURL: {r.url}\n" +
                       "\n".join(f"  - {s}" for s in r.snippets[:3]))
        return "\n\n".join(out)

    def _tool_scan_community(self, inp: dict) -> str:
        hours = inp.get("hours", 72)
        lines = []

        # GitHub
        try:
            from ..social.github_responder import GitHubResponder
            gh = GitHubResponder(self.config)
            issues = gh.find_issues(since_hours=hours, limit=10)
            if issues:
                lines.append("=== GITHUB ISSUES ===")
                for i in issues:
                    lines.append(f"- [{i['repo']}] {i['title']} by {i['user']}")
                    if i.get('body'):
                        lines.append(f"  {i['body'][:100]}")
                    lines.append(f"  {i['url']}")
            else:
                lines.append("GitHub: No recent issues found.")
        except Exception as e:
            lines.append(f"GitHub scan error: {e}")

        # Reddit
        try:
            from ..social.reddit import RedditClient
            reddit = RedditClient(self.config)
            posts = reddit.find_posts(since_hours=hours, limit=15)
            if posts:
                pain_points = [p for p in posts if p.get('signal_type') == 'pain_point']
                mentions = [p for p in posts if p.get('signal_type') == 'product_mention']
                if pain_points:
                    lines.append("\n=== TRENDING DEVELOPER PAIN POINTS (content opportunities) ===")
                    for p in pain_points[:8]:
                        lines.append(f"- [r/{p['subreddit']}] {p['title']} ({p['score']} pts, {p['num_comments']} comments)")
                        if p.get('body'):
                            lines.append(f"  {p['body'][:100]}")
                if mentions:
                    lines.append("\n=== PRODUCT MENTIONS (respond) ===")
                    for p in mentions[:5]:
                        lines.append(f"- [r/{p['subreddit']}] {p['title']} ({p['score']} pts)")
                        lines.append(f"  {p['url']}")
            else:
                lines.append("Reddit: No recent posts found.")
        except Exception as e:
            lines.append(f"Reddit scan error: {e}")

        return "\n".join(lines) if lines else "No community signals found."

    def _tool_write_content(self, inp: dict, ledger_ctx, console=None) -> str:
        """Write content using the agentic content writer (multi-turn, not pipeline)."""
        topic = inp["topic"]
        content_type = inp.get("content_type", "tutorial")
        guidance = inp.get("guidance", "")

        return _agentic_content_writer(
            topic, content_type, guidance,
            self.config, self.db, self.search_index, ledger_ctx, console,
        )

    def _tool_draft_tweet(self, inp: dict) -> str:
        from ..social.twitter import TwitterClient
        client = TwitterClient(self.config)
        if inp.get("thread"):
            tweets = client.draft_thread(inp["topic"], self.search_index, count=4)
            return "Thread draft:\n" + "\n---\n".join(t["tweet"] for t in tweets)
        else:
            result = client.draft_tweet(self.search_index, topic=inp["topic"])
            return f"Tweet draft:\n{result['tweet']}"

    def _tool_post_tweet(self, inp: dict) -> str:
        """Autonomously research, draft, and post a tweet."""
        from .firewall import check as fw_check
        verdict = fw_check("post_tweet", {
            "dry_run": self.config.dry_run,
            "critic_verdict": "approved",
        })
        if not verdict:
            return f"Firewall blocked: {verdict.reason}"
        from ..social.twitter import TwitterClient
        from ..community.tracker import log_interaction
        from ..models import CommunityInteraction, InteractionIntent, InteractionChannel
        from ..db import now_iso
        client = TwitterClient(self.config)
        result = client.autonomous_post(
            self.search_index,
            topic=inp["topic"],
            thread=inp.get("thread", False),
        )
        # Log tweets to community_interactions for site rendering
        if result.get("tweets"):
            for t in result["tweets"]:
                status = "sent" if t.get("id") else "draft"
                log_interaction(self.db, CommunityInteraction(
                    channel=InteractionChannel.TWITTER,
                    thread_url="",
                    counterpart="",
                    intent=InteractionIntent.ENGAGE,
                    question=inp.get("topic", ""),
                    draft_response=t.get("text", ""),
                    status=status,
                    notes=t.get("critic_verdict", result.get("critic_verdict", "")),
                    created_at=now_iso(),
                ))
        if result["status"] == "posted":
            tweets_summary = "\n".join(
                f"  {t['position']}: {t['text'][:80]}... (ID: {t['id']})"
                for t in result["tweets"]
            )
            return f"Posted {result['count']} tweet(s) to @RevenueCat_agad:\n{tweets_summary}"
        elif result["status"] == "partial":
            return f"Partial post — some tweets failed: {json.dumps(result['tweets'], indent=2)[:500]}"
        else:
            return f"Post failed: {result.get('reason', 'unknown')}"

    def _tool_generate_feedback(self, inp: dict, ledger_ctx) -> str:
        from ..feedback.collector import generate_feedback_from_docs
        count = inp.get("count", 2)
        items = generate_feedback_from_docs(
            self.search_index, self.config, self.db, ledger_ctx, count=count,
        )
        if not items:
            return "No feedback generated."
        lines = []
        for fb in items:
            lines.append(f"[{fb.severity.value}] {fb.title} ({fb.area.value})")
            lines.append(f"  Repro: {fb.repro_steps[:100]}")
            lines.append(f"  Fix: {fb.proposed_fix[:100]}")
        return "\n".join(lines)

    def _tool_draft_response(self, inp: dict, ledger_ctx) -> str:
        from ..knowledge.search import search as search_docs
        from ..community.responder import draft_response
        from ..community.tracker import log_interaction
        from ..models import CommunityInteraction, InteractionChannel, InteractionIntent

        results = search_docs(inp["question"], self.search_index, self.config.docs_cache_dir, top_k=5)
        response = draft_response(inp["question"], results, self.config, ledger_ctx)

        # Log to DB
        interaction = CommunityInteraction(
            channel=InteractionChannel(inp.get("channel", "other")),
            thread_url=inp.get("context", ""),
            intent=InteractionIntent.ANSWER_QUESTION,
            question=inp["question"],
            draft_response=response,
            status="draft",
            created_at=now_iso(),
        )
        log_interaction(self.db, interaction)

        return f"Response drafted:\n{response}"

    def _tool_evaluate(self, inp: dict) -> str:
        """Self-evaluation using Claude — the agent critiques its own work."""
        self._ensure_client()

        content = inp["content"]
        content_type = inp.get("content_type", "content")
        criteria = inp.get("criteria", "")

        eval_prompt = f"""Evaluate this {content_type} critically. Be brutally honest.

Check:
1. Is every factual claim backed by a citation?
2. Does it solve a real developer problem (not just list features)?
3. Would a developer building a subscription app find this USEFUL?
4. Is there anything misleading, vague, or wrong?
5. What specific improvements would make this better?

{f'Additional criteria: {criteria}' if criteria else ''}

Content to evaluate:
{content[:3000]}

Give a score from 1-10 and specific actionable feedback."""

        response = self._client.messages.create(
            model=self.config.ai_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": eval_prompt}],
        )
        return response.content[0].text

    def _tool_decide(self, inp: dict) -> str:
        """Planning tool — just echoes back the decision for the agent's reasoning trace."""
        observations = inp.get("observations", "")
        options = inp.get("options", [])
        decision = inp.get("decision", "")
        return (
            f"Decision recorded.\n"
            f"Observations: {observations[:200]}\n"
            f"Options considered: {', '.join(options[:5])}\n"
            f"Decision: {decision}"
        )

    def _tool_build_site(self) -> str:
        from ..site.generator import build_site
        page_count = build_site(self.db, self.config)
        return f"Site built: {page_count} pages generated."

    def _tool_publish_devto(self) -> str:
        """Publish all verified content to Dev.to."""
        from ..social.devto import DevToClient
        from ..db import update_row
        client = DevToClient(self.config)

        verified = query_rows(self.db, "content_pieces", where={"status": "verified"})
        unpublished = [c for c in verified if not c.get("devto_article_id")]

        if not unpublished:
            return "No verified unpublished content to publish."

        results = []
        for piece in unpublished:
            result = client.publish_from_content_piece(piece)
            if result.get("status") == "published":
                update_row(self.db, "content_pieces", piece["id"], {
                    "status": "published",
                    "devto_article_id": result.get("id"),
                    "devto_url": result.get("url", ""),
                    "published_at": now_iso(),
                })
                results.append(f"Published: {piece['title'][:50]} → {result.get('url', '')}")
            else:
                results.append(f"Failed: {piece['title'][:50]} — {result.get('status')}")

        return "\n".join(results) if results else "Nothing published."

    def _tool_sync_devto_stats(self) -> str:
        """Sync engagement stats from Dev.to back to DB."""
        from ..social.devto import DevToClient
        from ..db import update_row
        client = DevToClient(self.config)

        if not self.config.has_devto:
            return "No Dev.to API key configured."

        stats = client.get_all_stats()
        if not stats:
            return "No Dev.to articles found."

        synced = 0
        lines = ["Dev.to engagement stats:"]
        for s in stats:
            lines.append(f"  {s.get('title', '')[:50]}: {s['page_views']} views, "
                         f"{s['reactions']} reactions, {s['comments']} comments")

            # Match back to content piece by article ID or title
            published = query_rows(self.db, "content_pieces", where={"status": "published"})
            for p in published:
                if p.get("devto_article_id") == s.get("id") or (
                    p.get("title", "").lower()[:30] == s.get("title", "").lower()[:30]
                ):
                    update_row(self.db, "content_pieces", p["id"], {
                        "devto_article_id": s.get("id"),
                        "devto_url": s.get("url", ""),
                        "devto_views": s["page_views"],
                        "devto_reactions": s["reactions"],
                        "devto_comments": s["comments"],
                        "devto_synced_at": now_iso(),
                    })
                    synced += 1
                    break

        lines.append(f"\nSynced stats for {synced} articles back to DB.")
        return "\n".join(lines)

    def _tool_record_lesson(self, inp: dict, ledger_ctx) -> str:
        """Record a lesson to persistent memory."""
        from ..db import insert_row
        insert_row(self.db, "agent_memory", {
            "cycle_id": ledger_ctx.run_id if ledger_ctx else "",
            "lesson_type": inp["lesson_type"],
            "key": inp["key"],
            "insight": inp["insight"],
            "evidence": inp.get("evidence", ""),
            "confidence": inp.get("confidence", 0.5),
            "created_at": now_iso(),
        })
        return f"Lesson recorded: [{inp['lesson_type']}] {inp['key']}: {inp['insight'][:80]}"


def _agentic_content_writer(
    topic: str,
    content_type: str,
    guidance: str,
    config: Config,
    db,
    search_index,
    ledger_ctx,
    console=None,
) -> str:
    """Agentic content writer — multi-turn tool-use loop for content generation.

    Unlike the pipeline (outline → write), this agent:
    1. Researches the topic across multiple doc queries
    2. Identifies the specific developer pain point to address
    3. Plans the structure based on what it found
    4. Writes with citations
    5. Self-critiques and revises if needed
    """
    import anthropic
    from ..ledger import log_tool_call

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    writer_tools = [
        {
            "name": "search_docs",
            "description": "Search RevenueCat documentation. Returns ranked results with snippets and URLs.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "fetch_doc_page",
            "description": "Fetch the full content of a specific doc page by URL. Use this when you need more detail than search snippets provide.",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        {
            "name": "check_existing_content",
            "description": "Check what content already exists to avoid duplication.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "submit_article",
            "description": "Submit the final article. Call this when you're satisfied with the quality.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body_md": {"type": "string", "description": "Full article in Markdown with YAML front matter"},
                },
                "required": ["title", "body_md"],
            },
        },
    ]

    writer_system = f"""\
You are a technical content writer creating a {content_type} about: {topic}
{f'Guidance: {guidance}' if guidance else ''}

Instructions:
1. RESEARCH FIRST — search docs multiple times from different angles. Don't write from one search.
2. FIND THE PAIN — what specific developer problem does this topic address?
3. PLAN — decide on structure based on what you actually found in the docs.
4. WRITE — create the article with real citations to docs you actually read.
5. SELF-CHECK — before submitting, verify your citations reference real content.

RULES:
- Every factual claim needs [Source](url) citation
- Code examples must use real RevenueCat API patterns from the docs
- Start with the developer's problem, not the product feature
- Include a ## Sources section at the end
- Write in Markdown with YAML front matter (title, date, type)
- Aim for 800-1500 words of substance

Call submit_article when the article meets your quality bar.\
"""

    messages = [{"role": "user", "content": f"Write a {content_type} about: {topic}. Research thoroughly first."}]
    result_title = None
    result_body = None

    import sys
    for turn in range(12):
        time.sleep(0.3)
        print(f"[CONTENT-WRITER] Turn {turn+1}/12", file=sys.stderr, flush=True)
        response = client.messages.create(
            model=config.ai_model,
            max_tokens=8192,
            system=writer_system,
            tools=writer_tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            # Check if there's substantial text that looks like an article
            for block in response.content:
                if hasattr(block, "text") and block.text and len(block.text) > 200:
                    result_body = block.text
                    result_title = topic
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if console:
                    console.print(f"    [dim][writer] {block.name}({json.dumps(block.input)[:80]})[/dim]")

                if ledger_ctx:
                    log_tool_call(ledger_ctx, f"writer.{block.name}",
                                  json.dumps(block.input)[:100], "")

                if block.name == "search_docs":
                    from ..knowledge.search import search as search_fn
                    results = search_fn(block.input["query"], search_index, config.docs_cache_dir, top_k=5)
                    out = []
                    for r in results:
                        out.append(f"**{r.title}** (score: {r.score:.2f})\nURL: {r.url}\n" +
                                   "\n".join(f"  - {s}" for s in r.snippets[:3]))
                    result_text = "\n\n".join(out) if out else "No results."
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result_text})

                elif block.name == "fetch_doc_page":
                    import requests as req
                    try:
                        url = block.input["url"]
                        if not url.endswith(".md"):
                            url = url.rstrip("/") + ".md"
                        resp = req.get(url, timeout=15, headers={"User-Agent": "revcat-agent/1.0"})
                        content = resp.text[:8000]
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
                    except Exception as e:
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": f"Error: {e}"})

                elif block.name == "check_existing_content":
                    existing = query_rows(db, "content_pieces", order_by="created_at DESC", limit=10)
                    if existing:
                        lines = ["Existing content:"]
                        for c in existing:
                            lines.append(f"- [{c['content_type']}] {c['title']}")
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "\n".join(lines)})
                    else:
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "No existing content."})

                elif block.name == "submit_article":
                    result_title = block.input.get("title", topic)
                    result_body = block.input.get("body_md", "")
                    if not result_body:
                        # LLM sometimes puts article body in a text block instead of body_md param
                        # Check previous assistant content blocks for the article text
                        for prev_block in response.content:
                            if hasattr(prev_block, "text") and prev_block.text and len(prev_block.text) > 300:
                                result_body = prev_block.text
                                break
                    if not result_body:
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "ERROR: body_md is empty. You must include the full article markdown in the body_md parameter. Try again with submit_article including body_md."})
                        continue
                    print(f"[CONTENT-WRITER] submit_article: title={result_title[:50]}, body_len={len(result_body)}", file=sys.stderr, flush=True)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "Article submitted successfully."})

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        if result_body:
            break

    if not result_body:
        return "Content writer did not produce output after max turns."

    import re
    import os
    import sys
    from ..db import insert_row

    slug = re.sub(r'[^a-z0-9]+', '-', result_title.lower().strip()).strip('-')[:80]
    word_count = len(result_body.split())
    citations = len(set(re.findall(r'\[(?:Source|[^\]]+)\]\((https?://[^)]+)\)', result_body)))
    citation_urls = list(set(re.findall(r'\[(?:Source|[^\]]+)\]\((https?://[^)]+)\)', result_body)))
    sources_list = [{"url": url, "doc_sha256": "", "sections_cited": 1, "snippet_hashes": []} for url in citation_urls]

    # ── SAVE 1: File backup FIRST (never lose content) ──
    backup_dir = os.path.join(config.runs_dir, "articles")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"{slug}.md")
    with open(backup_path, "w") as f:
        f.write(result_body)
    print(f"[CONTENT-WRITER] Backup saved: {backup_path}", file=sys.stderr, flush=True)

    # ── SAVE 2: Site draft file ──
    from ..content.writer import save_draft
    save_draft(result_body, slug, config.site_output_dir)
    print(f"[CONTENT-WRITER] Site draft saved: {slug}", file=sys.stderr, flush=True)

    # ── SAVE 3: Database insert ──
    try:
        row_id = insert_row(db, "content_pieces", {
            "slug": slug,
            "title": result_title,
            "content_type": content_type,
            "status": "draft",
            "body_md": result_body,
            "sources_json": json.dumps(sources_list),
            "word_count": word_count,
            "citations_count": citations,
            "created_at": now_iso(),
        })
        print(f"[CONTENT-WRITER] DB insert OK: row_id={row_id}", file=sys.stderr, flush=True)
        if hasattr(db, 'sync'):
            db.sync()
    except Exception as e:
        print(f"[CONTENT-WRITER] DB insert failed ({e}), retrying with new slug", file=sys.stderr, flush=True)
        import time as time_mod
        slug = f"{slug[:70]}-{int(time_mod.time()) % 100000}"
        try:
            row_id = insert_row(db, "content_pieces", {
                "slug": slug,
                "title": result_title,
                "content_type": content_type,
                "status": "draft",
                "body_md": result_body,
                "sources_json": json.dumps(sources_list),
                "word_count": word_count,
                "citations_count": citations,
                "created_at": now_iso(),
            })
            print(f"[CONTENT-WRITER] DB retry OK: row_id={row_id}", file=sys.stderr, flush=True)
        except Exception as e2:
            print(f"[CONTENT-WRITER] DB retry also failed ({e2}). Article safe in {backup_path}", file=sys.stderr, flush=True)

    # ── EVAL GATE: post-write quality check ──
    from .firewall import eval_content, execute_rollback
    eval_result = eval_content({
        "citations_count": citations,
        "word_count": word_count,
        "body_md": result_body,
    })
    if not eval_result:
        rollback_msg = execute_rollback(eval_result, db, content_id=row_id if 'row_id' in dir() else None)
        print(f"[CONTENT-WRITER] Eval gate FAILED: {rollback_msg}", file=sys.stderr, flush=True)
        return f"Content written but quarantined (eval failed): {', '.join(eval_result.failures)}"

    return (
        f"Content written and saved:\n"
        f"Title: {result_title}\n"
        f"Type: {content_type}\n"
        f"Words: {word_count}\n"
        f"Citations: {citations}\n"
        f"Slug: {slug}"
    )
