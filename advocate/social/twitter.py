"""Twitter/X integration: draft and post tweets about RevenueCat.

All posting respects DRY_RUN. Drafts are always safe.
"""
import requests

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


class TwitterClient:
    def __init__(self, config: Config):
        self.config = config

    def draft_tweet(self, search_index, topic: str | None = None) -> dict:
        """Draft a single tweet using doc context. Never posts without approval."""
        from ..knowledge.search import search as search_docs

        if not topic:
            import random
            topic = random.choice(REVENUECAT_TOPICS)

        results = search_docs(topic, search_index, self.config.docs_cache_dir, top_k=3)

        if self.config.has_anthropic:
            tweet_text = self._draft_with_claude(topic, results)
        else:
            tweet_text = self._draft_from_results(topic, results)

        return {
            "tweet": tweet_text,
            "topic": topic,
            "status": "draft",
            "sources": [r.url for r in results[:2]],
        }

    def draft_thread(self, topic: str, search_index, count: int = 5) -> list[dict]:
        """Draft a tweet thread. Never posts without approval."""
        from ..knowledge.search import search as search_docs

        results = search_docs(topic, search_index, self.config.docs_cache_dir, top_k=5)

        if self.config.has_anthropic:
            tweets = self._draft_thread_with_claude(topic, results, count)
        else:
            tweets = self._draft_thread_from_results(topic, results, count)

        return tweets

    def post_tweet(self, text: str) -> dict | None:
        """Post a tweet. Blocked by DRY_RUN and requires credentials."""
        if self.config.dry_run:
            return {"status": "blocked_dry_run", "text": text}

        if not self.config.has_twitter:
            return {"status": "no_credentials", "text": text}

        # OAuth 1.0a posting via Twitter API v2
        from requests_oauthlib import OAuth1

        auth = OAuth1(
            self.config.twitter_api_key,
            self.config.twitter_api_secret,
            self.config.twitter_access_token,
            self.config.twitter_access_secret,
        )
        resp = requests.post(
            "https://api.twitter.com/2/tweets",
            json={"text": text},
            auth=auth,
            timeout=15,
        )
        if resp.status_code == 201:
            data = resp.json()
            return {"status": "posted", "id": data["data"]["id"]}
        return {"status": "error", "code": resp.status_code, "body": resp.text}

    def _draft_with_claude(self, topic, results) -> str:
        import time
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        doc_context = "\n".join(
            f"- {r.title}: {' '.join(r.snippets[:1])}" for r in results[:3]
        )

        time.sleep(0.5)
        message = client.messages.create(
            model=self.config.ai_model,
            max_tokens=200,
            system=(
                "You are a developer advocate for RevenueCat. "
                "Write a single tweet (max 280 chars) about the given topic. "
                "Be specific and technical, not generic marketing. "
                "Include one concrete fact from the docs. No hashtags."
            ),
            messages=[{"role": "user", "content": f"Topic: {topic}\n\nDocs:\n{doc_context}"}],
        )
        return message.content[0].text.strip()

    def _draft_from_results(self, topic, results) -> str:
        if results:
            snippet = results[0].snippets[0][:150] if results[0].snippets else topic
            return f"{snippet}: {results[0].url}"
        return f"Exploring {topic} with RevenueCat."

    def _draft_thread_with_claude(self, topic, results, count) -> list[dict]:
        import time
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        doc_context = "\n\n".join(
            f"**{r.title}** ({r.url}):\n" + "\n".join(f"- {s}" for s in r.snippets[:2])
            for r in results[:5]
        )

        time.sleep(0.5)
        message = client.messages.create(
            model=self.config.ai_model,
            max_tokens=1500,
            system=(
                f"You are a developer advocate for RevenueCat. "
                f"Write a {count}-tweet thread about the given topic. "
                f"Each tweet must be under 280 characters. "
                f"Number them 1/{count}, 2/{count}, etc. "
                f"Be specific and technical. Cite docs where relevant. "
                f"Separate tweets with ---"
            ),
            messages=[{"role": "user", "content": f"Topic: {topic}\n\nDocs:\n{doc_context}"}],
        )

        raw = message.content[0].text.strip()
        parts = [p.strip() for p in raw.split("---") if p.strip()]
        return [{"position": f"{i+1}/{len(parts)}", "tweet": t, "status": "draft"} for i, t in enumerate(parts)]

    def _draft_thread_from_results(self, topic, results, count) -> list[dict]:
        tweets = [{"position": f"1/{count}", "tweet": f"Thread: {topic}", "status": "draft"}]
        for i, r in enumerate(results[:count - 1], 2):
            snippet = r.snippets[0][:200] if r.snippets else r.title
            tweets.append({"position": f"{i}/{count}", "tweet": f"{snippet}: {r.url}", "status": "draft"})
        return tweets
