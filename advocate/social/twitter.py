"""Twitter/X integration: agentic tweet generation and posting.

The tweet-writing agent has tools to search docs, fetch URLs, scan GitHub/Reddit,
and read past interactions before composing tweets. It decides what to research.

Uses Twitter API v2 with OAuth 1.0a (User Context) for posting.
All posting respects DRY_RUN. Drafts are always safe.
"""
import json as _json
import requests
from requests_oauthlib import OAuth1

from ..config import Config


REVENUECAT_TOPICS = [
    "RevenueCat subscription monetization",
    "in-app purchase best practices",
    "RevenueCat MCP server for AI agents",
    "RevenueCat Charts API analytics",
    "mobile subscription lifecycle management",
    "RevenueCat paywalls and offerings",
    "subscription churn optimization",
    "RevenueCat SDK integration",
]

AGENT_SYSTEM_PROMPT = """\
You are @RevenueCat_agad — an autonomous AI developer advocate and marketing advocate for RevenueCat.

Your job is to help mobile developers build better subscription apps AND grow RevenueCat's \
presence. You tweet about real problems developers face — billing edge cases, churn, paywall \
strategy, receipt validation nightmares, StoreKit/Play Billing pain — and share practical \
solutions that position RevenueCat as the go-to platform.

RESEARCH FIRST. Use your tools to:
1. Check what developers are actually asking on GitHub issues and Reddit RIGHT NOW
2. Search the docs for the specific solution or pattern that addresses that pain
3. Check your past tweets so you don't repeat yourself

Then write something a developer building a subscription app would find genuinely useful.

WHAT GOOD DEVELOPER ADVOCACY LOOKS LIKE:
- Start with the developer's problem, not the product
- "Handling subscription upgrades across iOS and Android is a nightmare" > "RevenueCat has an MCP server"
- Share specific insights, strategies, and architecture decisions
- Give people something they can use TODAY, not product feature lists
- Be the person in the room who's seen this problem 100 times and knows the shortcut
- Write like a human, not a bot. Conversational, punchy, opinionated.

WHAT TO AVOID:
- Config/setup details (boring — that's what docs are for, not tweets)
- Listing tool names, API endpoints, or CLI commands without explaining WHY they matter
- Writing a changelog or product spec disguised as a tweet
- "Here are 5 things about [feature]" lists that read like release notes
- Anything a developer reads and thinks "ok but why should I care"
- CODE SNIPPETS IN TWEETS. Never put code in a tweet — it looks terrible and unreadable.
- Don't include links unless absolutely necessary. Tweets without links get better reach.

HASHTAG STRATEGY:
- Use search_trending_hashtags to find relevant trending hashtags BEFORE writing.
- If a trending hashtag fits your tweet naturally, include ONE at the end.
- Only use hashtags that are genuinely relevant to the tweet content.
- Hashtags count toward the 280 char limit.
- If no trending hashtag fits, skip it — forced hashtags look desperate.

HARD RULES:
- STRICT 280 CHARACTER LIMIT per tweet. The API rejects anything over.
- Count EVERY character: spaces, newlines, punctuation, URLs (23 chars via t.co).
- Aim for 240 chars max to be safe (leaves room for a hashtag). Shorter hits harder.
- No emojis.
- No code snippets. Ever.
- No links unless the tweet genuinely needs one to make sense.
- One idea per tweet. Don't cram.

PREFER SINGLE TWEETS over threads. Only use threads when the topic genuinely requires multiple \
tweets to explain. Most topics fit in one punchy tweet.

Thread format (only when necessary):
- 1/, 2/, etc. at the start (counts toward limit).
- First tweet = the hook. A problem statement or bold claim. Under 240 chars.
- Keep it to 2-3 tweets max. Long threads lose people.
- NO code snippets in threads.
- Separate with --- on its own line.

Call submit_tweet or submit_thread when ready."""

# Tool definitions for the agentic tweet writer
TWITTER_AGENT_TOOLS = [
    {
        "name": "search_docs",
        "description": "Search RevenueCat's ingested documentation. Returns ranked results with snippets and source URLs. Use this to ground your tweets in real technical facts.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch any URL — RevenueCat doc pages, competitor docs, blog posts. Returns page content.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch"}},
            "required": ["url"],
        },
    },
    {
        "name": "search_trending_hashtags",
        "description": "Search for trending hashtags relevant to a topic. Returns hashtags that are currently popular on X/Twitter in the developer/tech space. Use this BEFORE writing your tweet to find a hashtag that fits naturally.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "Topic to find relevant trending hashtags for (e.g. 'mobile development', 'subscriptions', 'iOS')"}},
            "required": ["topic"],
        },
    },
    {
        "name": "scan_github_issues",
        "description": "Scan RevenueCat's GitHub repos for recent issues. See what developers are struggling with right now.",
        "input_schema": {
            "type": "object",
            "properties": {"hours": {"type": "integer", "description": "Look back N hours", "default": 72}},
            "required": [],
        },
    },
    {
        "name": "scan_reddit",
        "description": "Scan developer subreddits for RevenueCat and subscription-related discussions.",
        "input_schema": {
            "type": "object",
            "properties": {"hours": {"type": "integer", "description": "Look back N hours", "default": 72}},
            "required": [],
        },
    },
    {
        "name": "get_past_interactions",
        "description": "Get your past tweets and community interactions from the database. Avoid repeating yourself.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max entries to return", "default": 10}},
            "required": [],
        },
    },
    {
        "name": "submit_tweet",
        "description": "Submit and POST a single tweet. Call this when you're done researching. The tweet will be posted to @RevenueCat_agad immediately.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The tweet text (max 280 chars)"}},
            "required": ["text"],
        },
    },
    {
        "name": "submit_thread",
        "description": "Submit and POST a tweet thread. Each tweet separated by ---. The thread will be posted to @RevenueCat_agad immediately as a reply chain.",
        "input_schema": {
            "type": "object",
            "properties": {"thread_text": {"type": "string", "description": "Full thread with --- separators between tweets"}},
            "required": ["thread_text"],
        },
    },
]


class TwitterClient:
    def __init__(self, config: Config):
        self.config = config
        self._auth = None

    @property
    def auth(self) -> OAuth1:
        if self._auth is None:
            self._auth = OAuth1(
                self.config.twitter_api_key,
                self.config.twitter_api_secret,
                self.config.twitter_access_token,
                self.config.twitter_access_secret,
            )
        return self._auth

    def draft_tweet(self, search_index, topic: str | None = None) -> dict:
        """Draft a single tweet. If no topic given, picks from a predefined topic list."""
        if not self.config.has_anthropic:
            raise RuntimeError("Anthropic API key required for tweet drafting. Set ANTHROPIC_API_KEY.")

        if not topic:
            import random
            topic = random.choice(REVENUECAT_TOPICS)

        result, critic_verdict = self._run_agent(topic, search_index, thread=False)
        return {
            "tweet": result,
            "topic": topic,
            "status": "draft",
            "sources": [],
            "critic_verdict": critic_verdict,
        }

    def draft_thread(self, topic: str, search_index, count: int = 5) -> list[dict]:
        """Draft a multi-tweet thread. Requires Anthropic API key."""
        if not self.config.has_anthropic:
            raise RuntimeError("Anthropic API key required for thread drafting. Set ANTHROPIC_API_KEY.")

        raw, critic_verdict = self._run_agent(topic, search_index, thread=True, count=count)
        parts = [p.strip() for p in raw.split("---") if p.strip()]
        return [{"position": f"{i+1}/{len(parts)}", "tweet": t, "status": "draft", "critic_verdict": critic_verdict} for i, t in enumerate(parts)]

    def _search_trending_hashtags(self, topic: str) -> str:
        """Select a relevant hashtag from a curated map based on topic keywords."""
        # Curated developer/tech hashtags that are consistently relevant
        DEVELOPER_HASHTAGS = {
            "ios": ["#iOSDev", "#SwiftLang", "#SwiftUI", "#iOS", "#AppleDev"],
            "android": ["#AndroidDev", "#Kotlin", "#Android"],
            "flutter": ["#Flutter", "#FlutterDev", "#Dart"],
            "react native": ["#ReactNative", "#JavaScript", "#React"],
            "mobile": ["#MobileDev", "#AppDev", "#MobileFirst"],
            "subscription": ["#SaaS", "#Subscriptions", "#Monetization", "#InAppPurchase"],
            "indie": ["#IndieHacker", "#IndieDev", "#BuildInPublic", "#Startup"],
            "ai": ["#AI", "#AgenticAI", "#LLM", "#AIAgents"],
            "developer": ["#DevCommunity", "#CodeNewbie", "#100DaysOfCode", "#DevLife"],
            "storekit": ["#StoreKit", "#StoreKit2", "#iOSDev"],
            "billing": ["#GooglePlayBilling", "#AndroidDev", "#InAppPurchase"],
            "churn": ["#SaaS", "#Churn", "#Retention", "#Growth"],
            "paywall": ["#Monetization", "#Paywall", "#Conversion"],
            "app store": ["#AppStore", "#ASO", "#iOSDev"],
        }

        # Try Twitter trends API (WOEID 1 = worldwide)
        trending_from_api = []
        try:
            resp = requests.get(
                "https://api.twitter.com/1.1/trends/place.json",
                params={"id": 1},
                auth=self.auth,
                timeout=10,
            )
            if resp.status_code == 200:
                trends = resp.json()[0].get("trends", [])
                # Filter for relevant trends
                topic_words = topic.lower().split()
                for trend in trends[:30]:
                    name = trend["name"]
                    if name.startswith("#"):
                        name_lower = name.lower()
                        for word in topic_words:
                            if word in name_lower or name_lower.lstrip("#") in topic.lower():
                                trending_from_api.append(f"{name} (trending, {trend.get('tweet_volume', '?')} tweets)")
                                break
        except Exception:
            pass

        # Match curated hashtags by topic keywords
        matched = []
        topic_lower = topic.lower()
        for keyword, tags in DEVELOPER_HASHTAGS.items():
            if keyword in topic_lower:
                matched.extend(tags)

        # Always include broad dev hashtags
        if not matched:
            matched = ["#MobileDev", "#AppDev", "#DevCommunity"]

        lines = ["Relevant hashtags for your tweet:\n"]

        if trending_from_api:
            lines.append("TRENDING NOW (high visibility):")
            for h in trending_from_api[:5]:
                lines.append(f"  {h}")
            lines.append("")

        lines.append("CONSISTENTLY RELEVANT:")
        seen = set()
        for tag in matched:
            if tag not in seen:
                lines.append(f"  {tag}")
                seen.add(tag)

        lines.append("\nPick ONE that fits naturally at the end of your tweet. Don't force it.")
        return "\n".join(lines)

    def post_tweet(self, text: str, force: bool = False, reply_to: str | None = None,
                   community_id: str | None = None) -> dict | None:
        """Post a tweet via Twitter API v2 with OAuth 1.0a.

        Args:
            community_id: Post into a Twitter Community for organic reach.
                          Find IDs at twitter.com/i/communities/<id>.
        """
        if len(text) > 280:
            return {"status": "error", "reason": f"Tweet is {len(text)} chars, max 280", "text": text}

        if self.config.dry_run and not force:
            return {"status": "blocked_dry_run", "text": text}

        if not self.config.has_twitter:
            return {"status": "no_credentials", "text": text}

        payload = {"text": text}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}
        if community_id:
            payload["community_id"] = community_id

        resp = requests.post(
            "https://api.twitter.com/2/tweets",
            json=payload,
            auth=self.auth,
            timeout=15,
        )

        if resp.status_code == 201:
            data = resp.json()
            return {"status": "posted", "id": data["data"]["id"]}
        return {"status": "error", "code": resp.status_code, "body": resp.text}

    def autonomous_post(self, search_index, topic: str | None = None, thread: bool = False,
                        count: int = 4, community_id: str | None = None) -> dict:
        """Fully autonomous: research → draft → post. The social media agent handles everything.

        Args:
            community_id: Post into a Twitter Community for organic reach.

        Returns dict with posted tweet IDs, text, and status.
        """
        if not topic:
            import random
            topic = random.choice(REVENUECAT_TOPICS)

        if not self.config.has_anthropic:
            raise RuntimeError("Anthropic API key required for tweet posting. Set ANTHROPIC_API_KEY.")

        # Run the agentic loop to get the draft
        if thread:
            raw, critic_verdict = self._run_agent(topic, search_index, thread=True, count=count)
            parts = [p.strip() for p in raw.split("---") if p.strip()]
            tweets = parts
        else:
            raw, critic_verdict = self._run_agent(topic, search_index, thread=False)
            tweets = [raw]

        # Post autonomously
        posted = []
        last_id = None
        for i, text in enumerate(tweets):
            result = self.post_tweet(text, force=False, reply_to=last_id,
                                     community_id=community_id if i == 0 else None)
            if result and result.get("status") == "posted":
                last_id = result["id"]
                posted.append({"text": text, "id": last_id, "position": f"{i+1}/{len(tweets)}"})
                print(f"    [tweet-agent] Posted {i+1}/{len(tweets)}: {text[:60]}...")
            else:
                posted.append({"text": text, "error": result, "position": f"{i+1}/{len(tweets)}"})
                print(f"    [tweet-agent] Failed to post {i+1}/{len(tweets)}: {result}")
                break

        return {
            "status": "posted" if all("id" in p for p in posted) else "partial",
            "topic": topic,
            "tweets": posted,
            "count": len(posted),
        }

    # --- Critic agent ---

    CRITIC_PROMPT = """\
You are a harsh quality critic for tweets posted by @RevenueCat_agad, an AI developer advocate.

Review the draft tweet(s) below. You must REJECT if ANY of these are true:
- Contains code snippets (any code like variable = value, function calls, etc.)
- Contains links/URLs (unless the tweet genuinely needs one)
- Over 280 characters per tweet
- Reads like a product changelog or release notes
- Too generic or vague — no specific insight
- Uses emojis
- Sounds robotic or corporate — not like a real developer talking
- Thread is unnecessarily long (>3 tweets) when a single tweet would work
- Numbered lists that read like documentation

APPROVE if the tweet:
- Starts with a real developer problem
- Shares a specific, useful insight
- Sounds like a human developer advocate, not a bot
- Fits within 280 chars
- Would make a developer stop scrolling

Respond with ONLY one of:
APPROVED
or
REJECTED: <one-line reason why, and what to fix>"""

    def _critic_review(self, draft: str) -> tuple[bool, str]:
        """Run the critic agent on a draft. Returns (approved, feedback).

        First does hard programmatic checks (length, code detection),
        then runs an LLM critic for subjective quality.
        """
        # --- Hard checks first (no LLM needed) ---
        # Check each tweet in a thread
        if "---" in draft:
            parts = [p.strip() for p in draft.split("---") if p.strip()]
        else:
            parts = [draft.strip()]

        for i, part in enumerate(parts):
            if len(part) > 280:
                msg = f"REJECTED: Tweet {i+1} is {len(part)} chars (max 280). Shorten it."
                pass  # Logged via verdict return value
                return False, msg

        # Detect code snippets
        code_indicators = ["= ", "==", "!=", "()", "();", "->", "=>", ".text =", "import ", "def ", "func ", "let ", "var ", "const "]
        for indicator in code_indicators:
            if indicator in draft:
                msg = f"REJECTED: Contains code snippet ('{indicator}'). Rewrite without any code — describe the concept in plain English."
                pass  # Logged via verdict return value
                return False, msg

        # --- LLM critic for subjective quality ---
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        response = client.messages.create(
            model=self.config.ai_model,
            max_tokens=200,
            system=self.CRITIC_PROMPT,
            messages=[{"role": "user", "content": f"Review this draft:\n\n{draft}"}],
        )

        verdict = response.content[0].text.strip()

        if verdict.startswith("APPROVED"):
            return True, verdict
        return False, verdict

    # --- Agentic loop ---

    def _run_agent(self, topic: str, search_index, thread: bool = False, count: int = 5) -> tuple[str, str]:
        """Run the agentic tool-use loop for tweet composition with critic gate.

        Returns (tweet_text, critic_verdict) tuple.
        """
        import time
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)

        task = f"Write a {count}-tweet thread" if thread else "Write a single tweet"

        max_rewrites = 3
        critic_feedback = ""
        for attempt in range(max_rewrites):
            messages = [{"role": "user", "content": f"{task} about: {topic}\n\nResearch first using your tools, then submit."}]
            if attempt > 0 and critic_feedback:
                messages[0]["content"] += f"\n\nYour previous draft was rejected by the quality critic: {critic_feedback}\n\nFix the issues and try again."

            result_text = None

            for turn in range(12):
                time.sleep(0.3)
                response = client.messages.create(
                    model=self.config.ai_model,
                    max_tokens=2000,
                    system=AGENT_SYSTEM_PROMPT,
                    tools=TWITTER_AGENT_TOOLS,
                    messages=messages,
                )

                if response.stop_reason == "end_turn":
                    for block in response.content:
                        if hasattr(block, "text") and block.text and len(block.text) > 20:
                            result_text = block.text
                    break

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"    [tweet-agent] {block.name}({_json.dumps(block.input)[:80]})")
                        result = self._handle_tool(block.name, block.input, search_index)

                        if block.name == "submit_tweet":
                            result_text = block.input["text"]
                            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "Tweet submitted for review."})
                        elif block.name == "submit_thread":
                            result_text = block.input["thread_text"]
                            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "Thread submitted for review."})
                        else:
                            if len(result) > 8000:
                                result = result[:8000] + "\n... (truncated)"
                            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                if result_text:
                    break

            if not result_text:
                raise RuntimeError("Tweet agent did not produce output after max turns")

            # --- Critic gate: separate LLM reviews the draft ---
            approved, critic_feedback = self._critic_review(result_text)
            if approved:
                pass  # Approval logged in verdict
                verdict = f"APPROVED (attempt {attempt + 1}): {critic_feedback}"
                return result_text, verdict
            else:
                pass  # Rejection fed back into rewrite loop

        # If we exhausted rewrites, raise instead of posting rejected content
        raise RuntimeError(f"Tweet rejected by critic after {max_rewrites} attempts: {critic_feedback}")

    def _handle_tool(self, name: str, inp: dict, search_index) -> str:
        """Handle tool calls from the tweet-writing agent."""
        if name == "search_trending_hashtags":
            return self._search_trending_hashtags(inp.get("topic", "mobile development"))

        elif name == "search_docs":
            from ..knowledge.search import search as search_docs
            results = search_docs(inp["query"], search_index, self.config.docs_cache_dir, top_k=5)
            out = []
            for r in results:
                out.append(f"**{r.title}** (score: {r.score:.2f})\nURL: {r.url}\n" + "\n".join(f"  - {s}" for s in r.snippets[:2]))
            return "\n\n".join(out) if out else "No results."

        elif name == "fetch_url":
            try:
                resp = requests.get(inp["url"], timeout=15, headers={"User-Agent": "revcat-agent-advocate/1.0"})
                content = resp.text[:10000]
                return f"Status: {resp.status_code}\n\n{content}"
            except Exception as e:
                return f"Error: {e}"

        elif name == "scan_github_issues":
            try:
                from .github_responder import GitHubResponder
                gh = GitHubResponder(self.config)
                issues = gh.find_issues(since_hours=inp.get("hours", 72), limit=10)
                if not issues:
                    return "No recent issues found."
                return "\n".join(f"- [{i['repo']}] {i['title']} by {i['user']} ({i['url']})" for i in issues)
            except Exception as e:
                return f"Error scanning GitHub: {e}"

        elif name == "scan_reddit":
            try:
                from .reddit import RedditClient
                reddit = RedditClient(self.config)
                posts = reddit.find_posts(since_hours=inp.get("hours", 72), limit=10)
                if not posts:
                    return "No recent posts found."
                return "\n".join(f"- [r/{p['subreddit']}] {p['title']} ({p['score']} pts, {p['num_comments']} comments) {p['url']}" for p in posts)
            except Exception as e:
                return f"Error scanning Reddit: {e}"

        elif name == "get_past_interactions":
            from ..db import query_rows, init_db_from_config
            db = init_db_from_config(self.config)
            rows = query_rows(db, "community_interactions", order_by="created_at DESC", limit=inp.get("limit", 10))
            if not rows:
                return "No past interactions in database."
            return "\n".join(f"- [{r['channel']}] {r['question'][:60]} → {r['draft_response'][:100]}" for r in rows)

        elif name in ("submit_tweet", "submit_thread"):
            return inp.get("text", inp.get("thread_text", ""))

        return "Unknown tool."

