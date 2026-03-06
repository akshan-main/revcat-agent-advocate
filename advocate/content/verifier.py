import hashlib
import os
import py_compile
import re

import requests

from ..models import SourceCitation, VerificationResult


def verify_citations(body_md: str, timeout: int = 10) -> tuple[list[str], list[str]]:
    """Check all citation URLs are reachable. Returns (reachable, dead)."""
    pattern = r'\[(?:Source|[^\]]+)\]\((https?://[^)]+)\)'
    urls = list(set(re.findall(pattern, body_md)))

    reachable = []
    dead = []

    for url in urls:
        try:
            resp = requests.head(url, timeout=timeout, allow_redirects=True)
            if resp.status_code == 405:
                # HEAD not allowed, try GET
                resp = requests.get(url, timeout=timeout, allow_redirects=True, stream=True)
                resp.close()
            if resp.status_code < 400:
                reachable.append(url)
            else:
                dead.append(url)
        except requests.RequestException:
            dead.append(url)

    return reachable, dead


def verify_snippet_hashes(body_md: str, cache_dir: str) -> tuple[list[str], list[str]]:
    """Verify quoted doc snippets exist in cached docs. Returns (valid_hashes, invalid_hashes)."""
    # Extract blockquotes (> prefixed lines)
    blockquotes = re.findall(r'^>\s*(.+)$', body_md, re.MULTILINE)
    valid = []
    invalid = []

    pages_dir = os.path.join(cache_dir, "pages")
    if not os.path.isdir(pages_dir):
        return valid, invalid

    # Load all cached docs into a single searchable corpus per file
    cached_docs = {}
    for filename in os.listdir(pages_dir):
        if filename.endswith(".md"):
            with open(os.path.join(pages_dir, filename), "r") as f:
                cached_docs[filename] = f.read()

    for quote in blockquotes:
        quote = quote.strip()
        if len(quote) < 10:
            continue

        snippet_hash = hashlib.sha256(quote.encode()).hexdigest()

        # Check if this snippet exists in any cached doc
        found = False
        for content in cached_docs.values():
            if quote in content:
                found = True
                break

        if found:
            valid.append(snippet_hash)
        else:
            invalid.append(snippet_hash)

    return valid, invalid


def verify_doc_sha256(sources: list[SourceCitation], db_conn) -> tuple[list[str], list[str]]:
    """Verify doc_sha256 in citations matches doc_snapshots table. Returns (matches, mismatches)."""
    matches = []
    mismatches = []

    for source in sources:
        if not source.doc_sha256:
            continue

        row = db_conn.execute(
            "SELECT doc_sha256 FROM doc_snapshots WHERE url = ? ORDER BY fetched_at DESC LIMIT 1",
            [source.url],
        ).fetchone()

        if row and row["doc_sha256"] == source.doc_sha256:
            matches.append(source.url)
        elif row:
            mismatches.append(source.url)
        # If no row, we can't verify; skip

    return matches, mismatches


def verify_code_snippets(snippet_paths: list[str]) -> tuple[list[str], list[str]]:
    """Run syntax checks on code snippets. Returns (valid, errors)."""
    valid = []
    errors = []

    for path in snippet_paths:
        if path.endswith(".py"):
            try:
                py_compile.compile(path, doraise=True)
                valid.append(path)
            except py_compile.PyCompileError:
                errors.append(path)
        else:
            # For non-Python, just check the file exists and is non-empty
            if os.path.exists(path) and os.path.getsize(path) > 0:
                valid.append(path)
            else:
                errors.append(path)

    return valid, errors


def full_verify(
    body_md: str,
    sources: list[SourceCitation],
    snippet_paths: list[str],
    cache_dir: str,
    db_conn,
    skip_network: bool = False,
) -> VerificationResult:
    """Run all verification checks on a content piece."""
    details = []

    # Citation reachability
    if skip_network:
        reachable, dead = [], []
        details.append("Network verification skipped (offline mode)")
    else:
        reachable, dead = verify_citations(body_md)
    details.append(f"Citations: {len(reachable)} reachable, {len(dead)} dead")

    # Snippet hashes
    valid_hashes, invalid_hashes = verify_snippet_hashes(body_md, cache_dir)
    details.append(f"Snippet hashes: {len(valid_hashes)} valid, {len(invalid_hashes)} invalid")

    # Doc SHA256
    sha_matches, sha_mismatches = verify_doc_sha256(sources, db_conn)
    details.append(f"Doc SHA256: {len(sha_matches)} match, {len(sha_mismatches)} mismatch")

    # Code snippets
    valid_code, error_code = verify_code_snippets(snippet_paths)
    details.append(f"Code snippets: {len(valid_code)} valid, {len(error_code)} errors")

    # Check citation count: flag if zero citations when content references docs
    citation_pattern = r'\[(?:Source|[^\]]+)\]\((https?://[^)]+)\)'
    citation_count = len(set(re.findall(citation_pattern, body_md)))
    if citation_count == 0 and len(sources) > 0:
        details.append("WARNING: No citations found despite having source documents")
    elif citation_count == 0:
        details.append("Note: No citations (no source documents provided)")
    else:
        details.append(f"Citations found: {citation_count}")

    return VerificationResult(
        citations_all_reachable=(len(dead) == 0),
        dead_links=dead,
        snippet_syntax_valid=(len(error_code) == 0),
        doc_sha256_matches=(len(sha_mismatches) == 0),
        details=details,
    )
