import json
import os
import shutil
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from ..db import query_rows
from ..ledger import verify_chain


def _md_to_html(md_text: str) -> str:
    """Convert markdown to HTML using the markdown library."""
    import markdown
    # Strip YAML front matter
    if md_text.startswith("---"):
        parts = md_text.split("---", 2)
        if len(parts) >= 3:
            md_text = parts[2]
    return markdown.markdown(
        md_text,
        extensions=["fenced_code", "tables", "toc"],
    )


def build_site(db_conn, config):
    """Build the complete static site from DB and artifacts."""
    output_dir = config.site_output_dir
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")

    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=False)

    # Verify ledger chain
    chain = verify_chain(db_conn, config)
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Shared context
    shared = {
        "chain_status": chain,
        "site_title": "RevenueCat Advocate OS",
        "build_date": build_date,
    }

    # Ensure output dirs
    for subdir in ["apply", "ledger", "content", "experiments", "feedback", "runbook", "assets", "roi"]:
        os.makedirs(os.path.join(output_dir, subdir), exist_ok=True)

    # 1. Index page (redirect to /apply)
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write('<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url=/apply/"></head><body><a href="/apply/">Apply</a></body></html>')

    # 2. Apply page
    apply_content = query_rows(db_conn, "content_pieces", where={"slug": "application-letter"})
    apply_html = ""
    if apply_content:
        apply_html = _md_to_html(apply_content[0].get("body_md", ""))
    template = env.get_template("apply.html")
    with open(os.path.join(output_dir, "apply", "index.html"), "w") as f:
        f.write(template.render(**shared, content=apply_html))

    # 3. Ledger page
    runs = query_rows(db_conn, "run_log", order_by="sequence DESC")
    for run in runs:
        for field in ["inputs_json", "sources_json", "tool_calls_json", "outputs_json", "verification_json"]:
            if run.get(field) and isinstance(run[field], str):
                try:
                    run[field] = json.loads(run[field])
                except json.JSONDecodeError:
                    pass
    template = env.get_template("ledger.html")
    with open(os.path.join(output_dir, "ledger", "index.html"), "w") as f:
        f.write(template.render(**shared, runs=runs, json=json))

    # 4. Content pages
    content_pieces = query_rows(db_conn, "content_pieces", order_by="created_at DESC")
    seo_pages = query_rows(db_conn, "seo_pages", order_by="created_at DESC")
    template = env.get_template("content.html")
    with open(os.path.join(output_dir, "content", "index.html"), "w") as f:
        f.write(template.render(**shared, content_pieces=content_pieces, seo_pages=seo_pages))

    # Individual content pages
    detail_template = env.get_template("content_detail.html")
    all_slugs = []
    for piece in content_pieces:
        slug = piece["slug"]
        all_slugs.append(slug)
        slug_dir = os.path.join(output_dir, "content", slug)
        os.makedirs(slug_dir, exist_ok=True)
        body_html = _md_to_html(piece.get("body_md", ""))
        sources = json.loads(piece["sources_json"]) if piece.get("sources_json") else []
        verification = json.loads(piece["verification_json"]) if piece.get("verification_json") else {}
        with open(os.path.join(slug_dir, "index.html"), "w") as f:
            f.write(detail_template.render(
                **shared, piece=piece, body_html=body_html,
                sources=sources, verification=verification,
            ))

    # SEO pages as content detail too
    for page in seo_pages:
        slug = page["slug"]
        all_slugs.append(slug)
        slug_dir = os.path.join(output_dir, "content", slug)
        os.makedirs(slug_dir, exist_ok=True)
        body_html = _md_to_html(page.get("body_md", ""))
        with open(os.path.join(slug_dir, "index.html"), "w") as f:
            f.write(detail_template.render(
                **shared, piece=page, body_html=body_html,
                sources=[], verification={},
            ))

    # 5. Experiments page
    experiments = query_rows(db_conn, "growth_experiments", order_by="created_at DESC")
    for exp in experiments:
        for field in ["inputs_json", "outputs_json", "results_json"]:
            if exp.get(field) and isinstance(exp[field], str):
                try:
                    exp[field] = json.loads(exp[field])
                except json.JSONDecodeError:
                    pass
    template = env.get_template("experiments.html")
    with open(os.path.join(output_dir, "experiments", "index.html"), "w") as f:
        f.write(template.render(**shared, experiments=experiments, json=json))

    # 6. Feedback page
    feedback_rows = query_rows(db_conn, "product_feedback", order_by="created_at DESC")
    for fb in feedback_rows:
        if fb.get("evidence_links_json") and isinstance(fb["evidence_links_json"], str):
            try:
                fb["evidence_links_json"] = json.loads(fb["evidence_links_json"])
            except json.JSONDecodeError:
                pass
    template = env.get_template("feedback.html")
    with open(os.path.join(output_dir, "feedback", "index.html"), "w") as f:
        f.write(template.render(**shared, feedbacks=feedback_rows))

    # 7. Runbook page
    template = env.get_template("runbook.html")
    with open(os.path.join(output_dir, "runbook", "index.html"), "w") as f:
        f.write(template.render(**shared))

    # 7b. Weekly report page
    reports_dir = os.path.join(output_dir, "reports")
    reports = []
    if os.path.isdir(reports_dir):
        for fname in sorted(os.listdir(reports_dir), reverse=True):
            if fname.endswith(".md"):
                with open(os.path.join(reports_dir, fname), "r") as f:
                    md_content = f.read()
                reports.append({"filename": fname, "html_content": _md_to_html(md_content)})
    os.makedirs(os.path.join(output_dir, "weekly-report"), exist_ok=True)
    template = env.get_template("weekly_report.html")
    with open(os.path.join(output_dir, "weekly-report", "index.html"), "w") as f:
        f.write(template.render(**shared, reports=reports))

    # 7c. ROI page
    roi_path = os.path.join(reports_dir, "roi.md")
    roi_html = ""
    if os.path.exists(roi_path):
        with open(roi_path, "r") as f:
            roi_html = _md_to_html(f.read())
    roi_template_str = """{% extends "base.html" %}
{% block content %}
<div class="output-dashboard">
{{ roi_content }}
</div>
{% if not roi_content %}
<p>Run <code>revcat-advocate roi</code> to generate the output dashboard.</p>
{% endif %}
{% endblock %}"""
    roi_template = env.from_string(roi_template_str)
    with open(os.path.join(output_dir, "roi", "index.html"), "w") as f:
        f.write(roi_template.render(**shared, roi_content=roi_html, page_title="Output"))

    # 7d. Intelligence reports page (doc quality, competitors, sentiment)
    intel_reports = []
    for report_name in ["doc_quality.md", "competitive_intel.md"]:
        rpath = os.path.join(reports_dir, report_name)
        if os.path.exists(rpath):
            with open(rpath, "r") as f:
                intel_reports.append({
                    "name": report_name.replace(".md", "").replace("_", " ").title(),
                    "html": _md_to_html(f.read()),
                })

    # 8. Copy CSS
    src_css = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(src_css):
        shutil.copy2(src_css, os.path.join(output_dir, "assets", "style.css"))

    # 9. Generate sitemap.xml
    base_url = ""
    if config.has_github:
        parts = config.github_repo.split("/")
        if len(parts) >= 2:
            base_url = f"https://{parts[0]}.github.io/{parts[1]}"
    _generate_sitemap(output_dir, base_url, all_slugs, build_date)

    # 10. Generate robots.txt
    _generate_robots(output_dir, base_url)

    # Count pages: index, apply, ledger, content index, experiments, feedback, runbook, roi, weekly-report + individual content
    page_count = 9 + len(content_pieces) + len(seo_pages)
    return page_count


def _generate_sitemap(output_dir: str, base_url: str, content_slugs: list[str], build_date: str):
    """Generate sitemap.xml for search engines."""
    pages = [
        ("", "1.0"),
        ("apply/", "1.0"),
        ("content/", "0.9"),
        ("experiments/", "0.7"),
        ("feedback/", "0.7"),
        ("ledger/", "0.6"),
        ("runbook/", "0.5"),
    ]
    for slug in content_slugs:
        pages.append((f"content/{slug}/", "0.8"))

    urls = []
    for path, priority in pages:
        urls.append(
            f"  <url>\n"
            f"    <loc>{base_url}/{path}</loc>\n"
            f"    <lastmod>{build_date[:10]}</lastmod>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n"
        '</urlset>\n'
    )

    with open(os.path.join(output_dir, "sitemap.xml"), "w") as f:
        f.write(sitemap)


def _generate_robots(output_dir: str, base_url: str):
    """Generate robots.txt."""
    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    with open(os.path.join(output_dir, "robots.txt"), "w") as f:
        f.write(robots)
