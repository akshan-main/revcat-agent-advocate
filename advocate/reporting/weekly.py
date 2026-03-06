import json
import os
from datetime import datetime, timedelta, timezone

from ..db import rows_since, now_iso
from ..ledger import verify_chain


def generate_weekly_report(
    db_conn,
    config=None,
    charts_client=None,
    week_start: str | None = None,
) -> str:
    """Generate a weekly activity report from the database."""
    if week_start is None:
        week_start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    week_end = now_iso()

    # Query each table
    content = rows_since(db_conn, "content_pieces", week_start)
    seo = rows_since(db_conn, "seo_pages", week_start)
    experiments = rows_since(db_conn, "growth_experiments", week_start)
    interactions = rows_since(db_conn, "community_interactions", week_start)
    feedback = rows_since(db_conn, "product_feedback", week_start)
    runs = rows_since(db_conn, "run_log", week_start, date_col="started_at")

    # Chain verification
    chain = verify_chain(db_conn, config)
    chain_status = "Verified" if chain.valid else f"BROKEN at entries {chain.breaks}"

    lines = [
        f"# Weekly Report: {week_start[:10]} to {week_end[:10]}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Content published | {len(content)} |",
        f"| SEO pages generated | {len(seo)} |",
        f"| Experiments active | {len(experiments)} |",
        f"| Community interactions | {len(interactions)} |",
        f"| Product feedback filed | {len(feedback)} |",
        f"| Ledger entries | {len(runs)} |",
        f"| Chain status | {chain_status} |",
        "",
    ]

    # Content Published
    lines.append("## Content Published")
    lines.append("")
    if content:
        for c in content:
            lines.append(f"- **{c['title']}** ({c['content_type']}): {c['word_count']} words, {c['citations_count']} citations")
    else:
        lines.append("No content published this week.")
    lines.append("")

    # SEO Pages
    if seo:
        lines.append("## SEO Pages Generated")
        lines.append("")
        for s in seo:
            lines.append(f"- **{s['title']}** ({s['template_type']}): /{s['slug']}")
        lines.append("")

    # Growth Experiments
    lines.append("## Growth Experiments")
    lines.append("")
    if experiments:
        for e in experiments:
            results = json.loads(e["results_json"]) if e.get("results_json") else {}
            lines.append(f"- **{e['name']}** [{e['status']}]")
            lines.append(f"  - Hypothesis: {e['hypothesis']}")
            if results:
                lines.append(f"  - Results: {json.dumps(results)}")
    else:
        lines.append("No experiments this week.")
    lines.append("")

    # Community Interactions
    lines.append("## Community Interactions")
    lines.append("")
    if interactions:
        # Count by channel
        by_channel: dict[str, int] = {}
        for i in interactions:
            ch = i["channel"]
            by_channel[ch] = by_channel.get(ch, 0) + 1
        for ch, cnt in by_channel.items():
            lines.append(f"- {ch}: {cnt} interactions")
        lines.append("")
        # Top 3 details
        lines.append("### Highlights")
        for i in interactions[:3]:
            lines.append(f"- [{i['channel']}] {i['question'][:100]}..." if i.get("question") else f"- [{i['channel']}] {i['intent']}")
    else:
        lines.append("No community interactions this week.")
    lines.append("")

    # Product Feedback
    lines.append("## Product Feedback")
    lines.append("")
    if feedback:
        for f_item in feedback:
            lines.append(f"- **{f_item['title']}** [{f_item['severity']}]: {f_item['area']}, {f_item['status']}")
    else:
        lines.append("No feedback filed this week.")
    lines.append("")

    # Charts snapshot
    if charts_client:
        lines.append("## Charts Snapshot")
        lines.append("")
        try:
            from ..revenuecat.charts import ChartsMetric
            week_start_date = week_start[:10]
            week_end_date = week_end[:10]
            for metric in [ChartsMetric.MRR, ChartsMetric.ACTIVE_SUBSCRIPTIONS]:
                data = charts_client.query_chart(metric, week_start_date, week_end_date)
                lines.append(charts_client.summarize(data))
                lines.append("")
        except Exception as e:
            lines.append(f"Charts data unavailable: {e}")
        lines.append("")

    # Ledger statistics
    lines.append("## Ledger Statistics")
    lines.append("")
    total_runs = chain.total_entries
    successful = len([r for r in runs if r.get("success", 1)])
    lines.append(f"- Total runs: {total_runs}")
    lines.append(f"- Successful: {successful}")
    lines.append(f"- Chain status: {chain_status}")
    if chain.hmac_verified is not None:
        lines.append(f"- HMAC verified: {'Yes' if chain.hmac_verified else 'No'}")
    lines.append("")

    return "\n".join(lines)


def save_report(report: str, output_dir: str) -> str:
    """Save weekly report to file."""
    reports_dir = os.path.join(output_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(reports_dir, f"week_{date_str}.md")
    with open(path, "w") as f:
        f.write(report)
    return path
