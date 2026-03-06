"""GitHub issue responder: scan RevenueCat repos for issues and draft cited responses.

All responses are drafts. Posting requires DRY_RUN=false and a GitHub token.
"""
import requests
from datetime import datetime, timezone, timedelta

from ..config import Config


MONITORED_REPOS = [
    "RevenueCat/purchases-ios",
    "RevenueCat/purchases-android",
    "RevenueCat/purchases-flutter",
    "RevenueCat/purchases-unity",
    "RevenueCat/purchases-kmp",
    "RevenueCat/purchases-js",
]


class GitHubResponder:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        if config.github_token:
            self.session.headers["Authorization"] = f"token {config.github_token}"
        self.session.headers["Accept"] = "application/vnd.github.v3+json"

    def find_issues(self, since_hours: int = 72, limit: int = 10) -> list[dict]:
        """Find recent open issues across monitored RevenueCat repos."""
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
        issues = []

        for repo in MONITORED_REPOS:
            try:
                resp = self.session.get(
                    f"https://api.github.com/repos/{repo}/issues",
                    params={"state": "open", "since": since, "per_page": limit, "sort": "created"},
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue

                for item in resp.json():
                    if item.get("pull_request"):
                        continue
                    issues.append({
                        "repo": repo,
                        "number": item["number"],
                        "title": item["title"],
                        "body": (item.get("body") or "")[:500],
                        "url": item["html_url"],
                        "user": item["user"]["login"],
                        "labels": [lbl["name"] for lbl in item.get("labels", [])],
                        "created_at": item["created_at"],
                    })
            except requests.RequestException:
                continue

        issues.sort(key=lambda x: x["created_at"], reverse=True)
        return issues[:limit]

    def draft_responses(self, issues: list[dict], search_index) -> list[dict]:
        """Draft responses for a batch of issues using doc context."""
        from ..knowledge.search import search as search_docs
        from ..community.responder import draft_response

        responses = []
        for issue in issues:
            query = f"{issue['title']} {issue['body'][:200]}"
            results = search_docs(query, search_index, self.config.docs_cache_dir, top_k=5)

            response_text = draft_response(query, results, self.config)

            responses.append({
                "issue": issue,
                "response": response_text,
                "sources": [r.url for r in results[:3]],
                "status": "draft",
            })

        return responses

    def post_comment(self, repo: str, issue_number: int, body: str) -> dict | None:
        """Post a comment on a GitHub issue. Blocked by DRY_RUN."""
        if self.config.dry_run:
            return {"status": "blocked_dry_run"}

        if not self.config.github_token:
            return {"status": "no_credentials"}

        resp = self.session.post(
            f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
            json={"body": body},
            timeout=15,
        )
        if resp.status_code == 201:
            return {"status": "posted", "url": resp.json()["html_url"]}
        return {"status": "error", "code": resp.status_code}
