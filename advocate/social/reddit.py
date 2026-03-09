"""Reddit integration: scan subreddits for developer pain points in the subscription/IAP space.

Finds trending problems developers face with mobile monetization — not just
RevenueCat mentions. A Growth Advocate brings developers TO the product by
solving problems they're already having.

All responses are drafts. Posting requires DRY_RUN=false and Reddit credentials.
"""
import requests
from datetime import datetime, timezone, timedelta

from ..config import Config


MONITORED_SUBREDDITS = [
    "iOSProgramming",
    "androiddev",
    "FlutterDev",
    "reactnative",
    "gamedev",
    "IndieDev",
    "SwiftUI",
    "KotlinMultiplatform",
]

# Broad developer pain point signals — NOT just "RevenueCat"
TRENDING_TERMS = [
    "in-app purchase rejected",
    "subscription billing",
    "paywall conversion",
    "StoreKit 2 migration",
    "Google Play Billing",
    "receipt validation",
    "subscription churn",
    "trial conversion rate",
    "app monetization strategy",
    "webhook subscription",
    "restore purchases",
    "family sharing subscriptions",
    "grace period billing",
    "offer codes promotional",
    "subscription analytics",
]

# Competitor and product-specific terms (lower priority)
PRODUCT_TERMS = [
    "RevenueCat",
    "Adapty",
    "Qonversion",
    "Superwall",
    "Glassfy",
]


class RedditClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "revcat-agent-advocate/1.0 (developer-advocate-bot)"

    def find_posts(self, since_hours: int = 72, limit: int = 20) -> list[dict]:
        """Scan Reddit for trending developer pain points in subscription/IAP space."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        posts = []

        # Phase 1: Broad pain point signals (most valuable — developers who don't know RC yet)
        for subreddit in MONITORED_SUBREDDITS[:6]:
            for term in TRENDING_TERMS[:8]:
                try:
                    resp = self.session.get(
                        f"https://www.reddit.com/r/{subreddit}/search.json",
                        params={"q": term, "sort": "relevance", "t": "month", "limit": 5, "restrict_sr": "on"},
                        timeout=15,
                    )
                    if resp.status_code != 200:
                        continue
                    for item in resp.json().get("data", {}).get("children", []):
                        post = item["data"]
                        created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
                        if created < cutoff:
                            continue
                        posts.append({
                            "subreddit": subreddit,
                            "title": post["title"],
                            "body": (post.get("selftext") or "")[:500],
                            "url": f"https://reddit.com{post['permalink']}",
                            "author": post.get("author", ""),
                            "score": post.get("score", 0),
                            "num_comments": post.get("num_comments", 0),
                            "created_at": created.isoformat(),
                            "signal_type": "pain_point",
                        })
                except requests.RequestException:
                    continue

        # Phase 2: Product mentions (respond to existing awareness)
        for subreddit in MONITORED_SUBREDDITS[:4]:
            for term in PRODUCT_TERMS[:3]:
                try:
                    resp = self.session.get(
                        f"https://www.reddit.com/r/{subreddit}/search.json",
                        params={"q": term, "sort": "new", "t": "week", "limit": 5, "restrict_sr": "on"},
                        timeout=15,
                    )
                    if resp.status_code != 200:
                        continue
                    for item in resp.json().get("data", {}).get("children", []):
                        post = item["data"]
                        created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
                        if created < cutoff:
                            continue
                        posts.append({
                            "subreddit": subreddit,
                            "title": post["title"],
                            "body": (post.get("selftext") or "")[:500],
                            "url": f"https://reddit.com{post['permalink']}",
                            "author": post.get("author", ""),
                            "score": post.get("score", 0),
                            "num_comments": post.get("num_comments", 0),
                            "created_at": created.isoformat(),
                            "signal_type": "product_mention",
                        })
                except requests.RequestException:
                    continue

        # Deduplicate by URL, sort by engagement
        seen = set()
        unique = []
        for p in posts:
            if p["url"] not in seen:
                seen.add(p["url"])
                unique.append(p)

        unique.sort(key=lambda x: (x["score"] + x["num_comments"] * 2), reverse=True)
        return unique[:limit]

    def draft_responses(self, posts: list[dict], search_index) -> list[dict]:
        """Draft responses for Reddit posts using doc context."""
        from ..knowledge.search import search as search_docs
        from ..community.responder import draft_response

        responses = []
        for post in posts:
            query = f"{post['title']} {post['body'][:200]}"
            results = search_docs(query, search_index, self.config.docs_cache_dir, top_k=5)
            response_text = draft_response(query, results, self.config)
            responses.append({
                "post": post,
                "response": response_text,
                "sources": [r.url for r in results[:3]],
                "status": "draft",
            })

        return responses

    def post_comment(self, post_url: str, body: str) -> dict | None:
        """Post a comment on Reddit. Blocked by DRY_RUN."""
        if self.config.dry_run:
            return {"status": "blocked_dry_run"}
        if not self.config.has_reddit:
            return {"status": "no_credentials"}
        return {"status": "not_implemented"}
