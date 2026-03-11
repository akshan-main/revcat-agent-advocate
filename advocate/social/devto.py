"""Dev.to integration: publish articles via the Forem API.

Dev.to has built-in SEO and discovery — articles surface organically via tags,
feed, and search. No existing audience required.

Uses Dev.to API v1: https://developers.forem.com/api/v1
Auth: API key from Settings → Extensions → DEV Community API Keys.
All posting respects DRY_RUN. Traction (views, reactions, comments) is
pulled back via get_article_stats() for closed-loop measurement.
"""
import json
import requests

from ..config import Config


DEVTO_API_BASE = "https://dev.to/api"

# Tags that perform well for RevenueCat-related content
REVENUECAT_TAGS = ["mobile", "ios", "android", "tutorial", "webdev", "beginners",
                   "flutter", "react", "saas", "monetization"]


class DevToClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        if config.devto_api_key:
            self.session.headers["api-key"] = config.devto_api_key
        self.session.headers["Content-Type"] = "application/json"
        self.session.headers["User-Agent"] = "revcat-agent-advocate/1.0"

    def publish_article(
        self,
        title: str,
        body_md: str,
        tags: list[str] | None = None,
        series: str | None = None,
        canonical_url: str | None = None,
        published: bool = True,
    ) -> dict:
        """Publish an article to Dev.to.

        Returns dict with status, url, id.
        """
        if self.config.dry_run:
            return {
                "status": "blocked_dry_run",
                "title": title,
                "tags": (tags or [])[:4],
                "body_length": len(body_md),
            }

        if not self.config.has_devto:
            return {"status": "no_credentials", "title": title}

        payload = {
            "article": {
                "title": title,
                "body_markdown": body_md,
                "published": published,
                "tags": (tags or self._auto_tags(title, body_md))[:4],
            }
        }

        if series:
            payload["article"]["series"] = series
        if canonical_url:
            payload["article"]["canonical_url"] = canonical_url

        resp = self.session.post(f"{DEVTO_API_BASE}/articles", json=payload, timeout=30)

        if resp.status_code == 201:
            data = resp.json()
            return {
                "status": "published" if published else "draft",
                "id": data["id"],
                "url": data["url"],
                "title": data["title"],
                "slug": data.get("slug", ""),
            }
        else:
            return {
                "status": "error",
                "code": resp.status_code,
                "body": resp.text[:500],
            }

    def get_articles(self, per_page: int = 10) -> list[dict]:
        """Get the authenticated user's published articles."""
        if not self.config.has_devto:
            return []

        resp = self.session.get(
            f"{DEVTO_API_BASE}/articles/me/published",
            params={"per_page": per_page},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def get_article_stats(self, article_id: int) -> dict | None:
        """Get engagement stats for a specific article.

        Returns: {page_views, reactions, comments, reading_time, published_at}
        """
        if not self.config.has_devto:
            return None

        resp = self.session.get(f"{DEVTO_API_BASE}/articles/{article_id}", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "page_views": data.get("page_views_count", 0),
                "reactions": data.get("public_reactions_count", 0),
                "comments": data.get("comments_count", 0),
                "reading_time": data.get("reading_time_minutes", 0),
                "published_at": data.get("published_at", ""),
                "url": data.get("url", ""),
                "title": data.get("title", ""),
            }
        return None

    def get_all_stats(self) -> list[dict]:
        """Get engagement stats for all published articles.

        Returns list of stat dicts, sorted by page_views descending.
        """
        articles = self.get_articles(per_page=30)
        stats = []
        for article in articles:
            stat = self.get_article_stats(article["id"])
            if stat:
                stat["id"] = article["id"]
                stats.append(stat)
        stats.sort(key=lambda s: s.get("page_views", 0), reverse=True)
        return stats

    def publish_and_track(self, db_conn, title: str, body_md: str,
                          tags: list[str] | None = None,
                          canonical_url: str | None = None) -> dict:
        """Publish and record in distribution queue for tracking.

        Uses the distribution pipeline for dedup, rate limiting, and tracking.
        """
        from ..distribution.pipeline import (
            DistributionItem, enqueue, check_rate_limit, record_post, record_failure,
        )

        # Check rate limit
        allowed, reason = check_rate_limit(db_conn, "dev_to")
        if not allowed:
            return {"status": "rate_limited", "reason": reason}

        # Enqueue for dedup + tracking
        item = DistributionItem(
            channel="dev_to",
            title=title,
            body=body_md,
            metadata={"tags": tags or [], "canonical_url": canonical_url or ""},
        )
        queue_id = enqueue(db_conn, item)
        if queue_id is None:
            return {"status": "duplicate", "title": title}

        # Publish
        result = self.publish_article(
            title=title,
            body_md=body_md,
            tags=tags,
            canonical_url=canonical_url,
        )

        # Record outcome
        if result.get("status") == "published":
            record_post(db_conn, queue_id, post_url=result.get("url", ""))
            result["queue_id"] = queue_id
        elif result.get("status") not in ("blocked_dry_run",):
            record_failure(db_conn, queue_id, json.dumps(result))

        return result

    def publish_from_content_piece(self, content_row: dict, site_base_url: str = "") -> dict:
        """Publish a content piece from the DB to Dev.to."""
        title = content_row.get("title", "Untitled")
        body_md = content_row.get("body_md", "")
        slug = content_row.get("slug", "")

        if not body_md:
            return {"status": "error", "reason": "Empty body"}

        canonical = None
        if site_base_url and slug:
            canonical = f"{site_base_url}/content/{slug}/"

        tags = self._auto_tags(title, body_md)

        return self.publish_article(
            title=title,
            body_md=body_md,
            tags=tags,
            canonical_url=canonical,
            published=True,
        )

    def _auto_tags(self, title: str, body: str) -> list[str]:
        """Pick up to 4 Dev.to tags based on content keywords."""
        text = (title + " " + body[:2000]).lower()

        tag_keywords = {
            "tutorial": ["how to", "getting started", "step", "guide"],
            "mobile": ["ios", "android", "mobile", "app"],
            "flutter": ["flutter", "dart"],
            "react": ["react native", "react"],
            "ios": ["swift", "swiftui", "storekit", "ios"],
            "android": ["kotlin", "android", "play billing"],
            "saas": ["subscription", "mrr", "churn", "revenue", "monetization"],
            "webdev": ["api", "webhook", "rest", "endpoint"],
            "beginners": ["getting started", "introduction", "basics"],
        }

        matched = []
        for tag, keywords in tag_keywords.items():
            for kw in keywords:
                if kw in text:
                    matched.append(tag)
                    break

        if "tutorial" not in matched:
            matched.insert(0, "tutorial")

        return matched[:4]
