import json
import os

import requests

from ..models import ProductFeedback
from ..config import Config
from ..db import update_row, query_rows


def export_to_markdown(feedback: ProductFeedback) -> str:
    """Render feedback as structured markdown."""
    evidence = "\n".join(f"- {link}" for link in feedback.evidence_links) if feedback.evidence_links else "None"

    return f"""# {feedback.title}

**Severity**: {feedback.severity.value} | **Area**: {feedback.area.value} | **Status**: {feedback.status}

## Reproduction Steps

{feedback.repro_steps or 'N/A'}

## Expected Behavior

{feedback.expected or 'N/A'}

## Actual Behavior

{feedback.actual or 'N/A'}

## Evidence

{evidence}

## Proposed Fix

{feedback.proposed_fix or 'N/A'}
"""


def export_to_github_issue(feedback: ProductFeedback, config: Config) -> str | None:
    """Create a GitHub issue from feedback. Returns issue URL or None."""
    if not config.has_github:
        return None
    if config.dry_run:
        return None

    body = export_to_markdown(feedback)
    labels = [feedback.severity.value, feedback.area.value, "advocate-os"]

    resp = requests.post(
        f"https://api.github.com/repos/{config.github_repo}/issues",
        headers={
            "Authorization": f"Bearer {config.github_token}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "title": f"[{feedback.severity.value}] [{feedback.area.value}] {feedback.title}",
            "body": body,
            "labels": labels,
        },
        timeout=30,
    )

    if resp.status_code == 201:
        return resp.json().get("html_url", "")
    return None


def export_batch(db_conn, config: Config, output_dir: str = "./site_output", status: str = "new") -> list[str]:
    """Export all feedback with given status. Returns list of paths/URLs."""
    rows = query_rows(db_conn, "product_feedback", where={"status": status})
    paths = []

    feedback_dir = os.path.join(output_dir, "feedback")
    os.makedirs(feedback_dir, exist_ok=True)

    for row in rows:
        fb = ProductFeedback(
            title=row["title"],
            severity=row["severity"],
            area=row["area"],
            repro_steps=row.get("repro_steps", ""),
            expected=row.get("expected", ""),
            actual=row.get("actual", ""),
            evidence_links=json.loads(row["evidence_links_json"]) if row.get("evidence_links_json") else [],
            proposed_fix=row.get("proposed_fix", ""),
            status=row["status"],
            created_at=row.get("created_at", ""),
        )

        md = export_to_markdown(fb)
        filename = f"feedback_{row['id']}.md"
        path = os.path.join(feedback_dir, filename)
        with open(path, "w") as f:
            f.write(md)
        paths.append(path)

        # Try GitHub issue export
        issue_url = export_to_github_issue(fb, config)
        if issue_url:
            update_row(db_conn, "product_feedback", row["id"], {
                "status": "submitted",
                "github_issue_url": issue_url,
            })
        else:
            update_row(db_conn, "product_feedback", row["id"], {"status": "exported"})

    return paths
