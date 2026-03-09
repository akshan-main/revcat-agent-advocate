import hashlib
import os
import re
from datetime import datetime, timezone

from ..models import ContentOutline, ContentPiece, SourceCitation
from ..db import insert_row, now_iso

WRITER_SYSTEM_PROMPT = """You are a technical writer for RevenueCat, creating content for developers \
building apps with in-app subscriptions. You are writing a {content_type}.

CRITICAL RULES:
1. Every factual claim about RevenueCat MUST include a citation in the format [Source](url).
2. Never fabricate features, API endpoints, pricing, or metrics that are not in the provided documentation.
3. Code examples must use real RevenueCat API patterns from the documentation.
4. If you are unsure about something, say "refer to the documentation" rather than guessing.
5. Include a ## Sources section at the end listing all cited documentation pages.

You will be provided with:
- A content outline with section headings and key points
- Relevant documentation snippets with their source URLs
- The content type (tutorial, case study, or agent playbook)

Write the complete article in Markdown with YAML front matter."""


def generate_draft(
    outline: ContentOutline,
    doc_snippets: dict[str, str],
    config=None,
    ledger_ctx=None,
) -> str:
    """Generate a full article draft from an outline and doc snippets."""
    if not config or not config.has_anthropic:
        raise RuntimeError("Anthropic API key required for content generation. Set ANTHROPIC_API_KEY.")
    return _generate_with_claude(outline, doc_snippets, config, ledger_ctx)


def _generate_with_claude(
    outline: ContentOutline,
    doc_snippets: dict[str, str],
    config,
    ledger_ctx=None,
) -> str:
    """Use Claude API to generate the draft."""
    import anthropic

    import time

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    model = config.ai_model

    # Build outline text
    outline_text = f"# {outline.title}\n\n"
    for section in outline.sections:
        outline_text += f"## {section.heading}\n"
        for point in section.key_points:
            outline_text += f"- {point}\n"
        if section.source_refs:
            outline_text += f"Sources: {', '.join(section.source_refs)}\n"
        outline_text += "\n"

    # Build doc context
    snippets_text = ""
    for url, content in list(doc_snippets.items())[:5]:
        snippets_text += f"\n--- Documentation: {url} ---\n{content[:2000]}\n"

    system = WRITER_SYSTEM_PROMPT.format(content_type=outline.content_type.value)

    time.sleep(0.5)  # Rate limit between API calls
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{
            "role": "user",
            "content": (
                f"Write this article based on the outline and documentation below.\n\n"
                f"OUTLINE:\n{outline_text}\n\n"
                f"DOCUMENTATION:\n{snippets_text}"
            ),
        }],
    )

    if ledger_ctx:
        from ..ledger import log_tool_call
        log_tool_call(
            ledger_ctx,
            "anthropic.messages.create",
            f"model={model}",
            f"tokens={message.usage.output_tokens}",
        )

    draft = message.content[0].text

    # Ensure front matter
    if not draft.startswith("---"):
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        front_matter = (
            f"---\n"
            f'title: "{outline.title}"\n'
            f'date: "{date}"\n'
            f"type: {outline.content_type.value}\n"
            f"---\n\n"
        )
        draft = front_matter + draft

    return draft



def save_draft(body_md: str, slug: str, output_dir: str) -> str:
    """Save a draft to the output directory."""
    post_dir = os.path.join(output_dir, "content", slug)
    os.makedirs(post_dir, exist_ok=True)
    path = os.path.join(post_dir, "index.md")
    with open(path, "w") as f:
        f.write(body_md)
    return path


def extract_code_snippets(body_md: str) -> list[tuple[str, str]]:
    """Extract code blocks from markdown. Returns [(language, code), ...]."""
    pattern = r'```(\w+)\n(.*?)```'
    matches = re.findall(pattern, body_md, re.DOTALL)
    return [(lang, code.strip()) for lang, code in matches]


def save_code_snippets(snippets: list[tuple[str, str]], slug: str, output_dir: str) -> list[str]:
    """Save code snippets alongside a post."""
    post_dir = os.path.join(output_dir, "content", slug)
    os.makedirs(post_dir, exist_ok=True)

    ext_map = {"python": "py", "javascript": "js", "typescript": "ts", "swift": "swift", "kotlin": "kt", "bash": "sh"}
    paths = []
    for i, (lang, code) in enumerate(snippets):
        ext = ext_map.get(lang, lang)
        path = os.path.join(post_dir, f"snippet_{i}.{ext}")
        with open(path, "w") as f:
            f.write(code)
        paths.append(path)
    return paths


def extract_citations(body_md: str) -> list[str]:
    """Extract all citation URLs from markdown."""
    # Match [Source](url) and [text](url) patterns
    pattern = r'\[(?:Source|[^\]]+)\]\((https?://[^)]+)\)'
    return list(set(re.findall(pattern, body_md)))


def build_source_citations(body_md: str, doc_snippets: dict[str, str]) -> list[SourceCitation]:
    """Build SourceCitation objects from a draft."""
    urls = extract_citations(body_md)
    citations = []
    for url in urls:
        content = doc_snippets.get(url, "")
        doc_sha256 = hashlib.sha256(content.encode()).hexdigest() if content else ""
        citations.append(SourceCitation(
            url=url,
            doc_sha256=doc_sha256,
            sections_cited=body_md.count(url),
        ))
    return citations


def record_content(db_conn, piece: ContentPiece) -> int:
    """Insert or update a content piece in the database."""
    return insert_row(db_conn, "content_pieces", {
        "slug": piece.slug,
        "title": piece.title,
        "content_type": piece.content_type.value,
        "status": piece.status,
        "body_md": piece.body_md,
        "outline_json": piece.outline.model_dump() if piece.outline else None,
        "sources_json": [s.model_dump() for s in piece.sources],
        "verification_json": piece.verification.model_dump() if piece.verification else None,
        "created_at": piece.created_at or now_iso(),
        "published_at": piece.published_at,
        "word_count": piece.word_count,
        "citations_count": piece.citations_count,
    }, or_replace=True)
