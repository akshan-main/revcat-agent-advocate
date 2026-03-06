"""Reddit integration: scan subreddits for RevenueCat-related posts and draft responses.

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
]

SEARCH_TERMS = [
    "RevenueCat",
    "in-app purchase",
    "subscription monetization",
    "StoreKit",
    "Google Play Billing",
]


class RedditClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "AdvocateOS/1.0 (developer-advocate-bot)"

    def find_posts(self, since_hours: int = 72, limit: int = 15) -> list[dict]:
        """Search Reddit for RevenueCat-related posts in monitored subreddits."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        posts = []

        for subreddit in MONITORED_SUBREDDITS:
            for term in SEARCH_TERMS[:2]:  # Limit queries to avoid rate limiting
                try:
                    resp = self.session.get(
                        f"https://www.reddit.com/r/{subreddit}/search.json",
                        params={"q": term, "sort": "new", "t": "week", "limit": 10, "restrict_sr": "on"},
                        timeout=15,
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json().get("data", {}).get("children", [])
                    for item in data:
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
                        })
                except requests.RequestException:
                    continue

        # Deduplicate by URL
        seen = set()
        unique = []
        for p in posts:
            if p["url"] not in seen:
                seen.add(p["url"])
                unique.append(p)

        unique.sort(key=lambda x: x["created_at"], reverse=True)
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

        # Reddit OAuth2 flow would go here
        return {"status": "not_implemented"}
