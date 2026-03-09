import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

PARALLEL_WORKERS = 10  # concurrent doc page fetches

LLM_INDEX_URL = "https://www.revenuecat.com/docs/assets/files/llms-b3277dc1a771ac4b43dc7cfb88ebd955.txt"
DOCS_BASE_URL = "https://www.revenuecat.com/docs"
RATE_LIMIT_SECONDS = 0.3
MAX_RETRIES = 3


@dataclass
class DocEntry:
    path: str
    title: str
    category: str
    url: str


@dataclass
class IngestReport:
    total_entries: int = 0
    fetched: int = 0
    skipped: int = 0
    errored: int = 0
    changed: int = 0
    errors: list[str] = field(default_factory=list)


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=MAX_RETRIES, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_index(cache_dir: str, demo_mode: bool = False) -> list[DocEntry]:
    """Download the LLM docs index and parse all doc entries."""
    os.makedirs(cache_dir, exist_ok=True)

    # In demo mode, use local fixture instead of fetching from network
    sample_path = os.path.join(os.path.dirname(__file__), '..', '..', 'demo', 'fixtures', 'sample_index.txt')
    if demo_mode and os.path.exists(sample_path):
        with open(sample_path) as f:
            raw = f.read()
    else:
        session = _make_session()
        resp = session.get(LLM_INDEX_URL, timeout=30)
        resp.raise_for_status()
        raw = resp.text

    # Save raw index
    index_path = os.path.join(cache_dir, "index.txt")
    with open(index_path, "w") as f:
        f.write(raw)

    return parse_index(raw)


def parse_index(raw_text: str) -> list[DocEntry]:
    """Parse the LLM index text into DocEntry objects."""
    entries = []
    current_category = "General"

    for line in raw_text.splitlines():
        line = line.strip()

        # Section headers (## or #)
        if line.startswith("#"):
            current_category = line.lstrip("#").strip()
            continue

        # Format 1: Markdown links — - [Title](url): description
        match = re.match(r'^-\s*\[([^\]]+)\]\(([^)]+)\)', line)
        if match:
            title = match.group(1)
            url = match.group(2)

            if url.startswith(DOCS_BASE_URL):
                path = url[len(DOCS_BASE_URL):].strip("/")
            elif url.startswith("/docs/"):
                path = url[len("/docs/"):].strip("/")
                url = f"{DOCS_BASE_URL}/{path}"
            elif url.startswith("https://"):
                continue
            else:
                path = url.strip("/")
                url = f"{DOCS_BASE_URL}/{path}"

            if path:
                entries.append(DocEntry(path=path, title=title, category=current_category, url=url))
            continue

        # Format 2: Plain path — - /path/to/page - Description text
        match = re.match(r'^-\s+(/[^\s]+)\s*(?:-\s*(.+))?$', line)
        if match:
            path = match.group(1).strip("/")
            title = match.group(2) or path.split("/")[-1].replace("-", " ").title()
            url = f"{DOCS_BASE_URL}/{path}"

            if path:
                entries.append(DocEntry(path=path, title=title, category=current_category, url=url))

    return entries


def _sanitize_path(path: str) -> str:
    """Convert URL path to safe filesystem path."""
    return path.replace("/", "__")


def fetch_doc_page(
    entry: DocEntry,
    cache_dir: str,
    session: requests.Session,
    force: bool = False,
) -> tuple[str | None, str | None]:
    """Fetch a single doc page's .md mirror. Returns (content, sha256) or (None, None) on error."""
    pages_dir = os.path.join(cache_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    cache_path = os.path.join(pages_dir, f"{_sanitize_path(entry.path)}.md")

    # Skip if cached and not forcing
    if os.path.exists(cache_path) and not force:
        with open(cache_path, "r") as f:
            content = f.read()
        return content, hashlib.sha256(content.encode()).hexdigest()

    # Fetch .md mirror
    md_url = f"{entry.url}.md"
    try:
        resp = session.get(md_url, timeout=30)
        resp.raise_for_status()
        content = resp.text
    except requests.RequestException:
        # Try without .md suffix as fallback
        try:
            resp = session.get(entry.url, timeout=30)
            resp.raise_for_status()
            content = resp.text
        except requests.RequestException:
            return None, None

    doc_sha256 = hashlib.sha256(content.encode()).hexdigest()

    with open(cache_path, "w") as f:
        f.write(content)

    return content, doc_sha256


def store_snapshot(db_conn, entry: DocEntry, doc_sha256: str, content_length: int):
    """Store or update a doc snapshot in the database."""
    from ..db import now_iso

    # Check for existing snapshot
    existing = db_conn.execute(
        "SELECT doc_sha256 FROM doc_snapshots WHERE url = ? ORDER BY fetched_at DESC LIMIT 1",
        [entry.url],
    ).fetchone()

    changed_from = None
    if existing and existing["doc_sha256"] != doc_sha256:
        changed_from = existing["doc_sha256"]

    db_conn.execute(
        "INSERT OR REPLACE INTO doc_snapshots (url, path, doc_sha256, content_length, fetched_at, changed_from) VALUES (?, ?, ?, ?, ?, ?)",
        [entry.url, entry.path, doc_sha256, content_length, now_iso(), changed_from],
    )
    db_conn.commit()


def _fetch_one(entry: DocEntry, cache_dir: str, session: requests.Session, force: bool, demo_mode: bool):
    """Fetch a single doc page. Returns (entry, content, doc_sha256, was_cached, error)."""
    cache_path = os.path.join(cache_dir, "pages", f"{_sanitize_path(entry.path)}.md")
    was_cached = os.path.exists(cache_path) and not force

    if demo_mode and not os.path.exists(cache_path):
        # Try to find a matching fixture file for this entry
        fixtures_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'demo', 'fixtures')
        matched = _match_demo_fixture(entry, fixtures_dir)
        if matched:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w") as f:
                f.write(matched)
            doc_sha256 = hashlib.sha256(matched.encode()).hexdigest()
            return entry, matched, doc_sha256, False, None
        # Generate minimal stub content so the page is indexable (DEMO ONLY)
        stub = f"# {entry.title}\n\n> **[DEMO STUB]** This is placeholder content generated in demo mode. Not sourced from RevenueCat documentation.\n\n{entry.title}. See {entry.url} for full documentation.\n"
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w") as f:
            f.write(stub)
        doc_sha256 = hashlib.sha256(stub.encode()).hexdigest()
        return entry, stub, doc_sha256, False, None

    try:
        content, doc_sha256 = fetch_doc_page(entry, cache_dir, session, force=force)
        return entry, content, doc_sha256, was_cached, None
    except Exception as e:
        return entry, None, None, False, str(e)


def _match_demo_fixture(entry: DocEntry, fixtures_dir: str) -> str | None:
    """Try to find a demo fixture file matching the entry path."""
    if not os.path.isdir(fixtures_dir):
        return None
    # Map known fixture names to path keywords
    mappings = {
        "charts": "sample_doc_charts.md",
        "authentication": "sample_doc_auth.md",
        "mcp": "sample_doc_mcp.md",
        "getting-started": "sample_doc_getting_started.md",
        "offerings": "sample_doc_offerings.md",
    }
    path_lower = entry.path.lower()
    for keyword, filename in mappings.items():
        if keyword in path_lower:
            fixture_path = os.path.join(fixtures_dir, filename)
            if os.path.exists(fixture_path):
                with open(fixture_path) as f:
                    return f.read()
    return None


def ingest_all(db_conn, config, force: bool = False) -> IngestReport:
    """Download all docs from the LLM index, cache locally, store snapshots."""
    report = IngestReport()
    cache_dir = config.docs_cache_dir

    demo_mode = getattr(config, 'demo_mode', False)
    entries = fetch_index(cache_dir, demo_mode=demo_mode)
    report.total_entries = len(entries)

    session = _make_session()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Ingesting docs...", total=len(entries))

        # Parallel fetching with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_one, entry, cache_dir, session, force, demo_mode): entry
                for entry in entries
            }

            for future in as_completed(futures):
                entry, content, doc_sha256, was_cached, error = future.result()

                if error == "demo_skip":
                    report.skipped += 1
                elif error:
                    report.errored += 1
                    report.errors.append(f"{entry.url}: {error}")
                elif content is None:
                    report.errored += 1
                    report.errors.append(f"Failed to fetch: {entry.url}")
                elif was_cached:
                    report.skipped += 1
                else:
                    report.fetched += 1

                if content and doc_sha256:
                    existing = db_conn.execute(
                        "SELECT doc_sha256 FROM doc_snapshots WHERE url = ? ORDER BY fetched_at DESC LIMIT 1",
                        (entry.url,),
                    ).fetchone()
                    if existing and existing["doc_sha256"] != doc_sha256:
                        report.changed += 1

                    store_snapshot(db_conn, entry, doc_sha256, len(content))

                progress.advance(task)

    return report
