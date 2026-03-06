import json
import math
import os
import re
from dataclasses import dataclass, field

from ..models import SearchResult

# BM25 parameters
K1 = 1.2
B = 0.75

STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "not", "with", "this", "that", "it", "be",
    "as", "by", "from", "has", "have", "had", "will", "can", "do", "does",
    "but", "if", "they", "you", "we", "he", "she", "its", "my", "your",
})


@dataclass
class Posting:
    doc_path: str
    term_frequency: int
    positions: list[int] = field(default_factory=list)


@dataclass
class SearchIndex:
    doc_count: int = 0
    avg_doc_length: float = 0.0
    inverted_index: dict[str, list[Posting]] = field(default_factory=dict)
    doc_lengths: dict[str, int] = field(default_factory=dict)
    doc_titles: dict[str, str] = field(default_factory=dict)
    doc_sha256s: dict[str, str] = field(default_factory=dict)
    doc_urls: dict[str, str] = field(default_factory=dict)


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, remove stopwords."""
    tokens = re.findall(r'[a-z0-9]+', text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def _extract_title(content: str) -> str:
    """Extract title from markdown content (first # heading)."""
    for line in content.splitlines()[:20]:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _path_to_url(path: str) -> str:
    """Convert sanitized cache path back to docs URL."""
    # Cache files are stored as path__subpath.md
    doc_path = path.replace("__", "/")
    if doc_path.endswith(".md"):
        doc_path = doc_path[:-3]
    return f"https://www.revenuecat.com/docs/{doc_path}"


def build_index(cache_dir: str, db_conn=None) -> SearchIndex:
    """Build BM25 search index from cached .md files."""
    pages_dir = os.path.join(cache_dir, "pages")
    if not os.path.isdir(pages_dir):
        return SearchIndex()

    index = SearchIndex()
    total_length = 0

    # Get sha256 mappings from DB if available
    sha256_map = {}
    if db_conn:
        rows = db_conn.execute("SELECT url, doc_sha256 FROM doc_snapshots").fetchall()
        for row in rows:
            sha256_map[row["url"]] = row["doc_sha256"]

    for filename in os.listdir(pages_dir):
        if not filename.endswith(".md"):
            continue

        filepath = os.path.join(pages_dir, filename)
        with open(filepath, "r") as f:
            content = f.read()

        doc_path = filename  # e.g., "dashboard-and-metrics__charts.md"
        url = _path_to_url(doc_path)
        title = _extract_title(content) or filename.replace("__", "/").replace(".md", "")

        tokens = tokenize(content)
        doc_length = len(tokens)

        index.doc_lengths[doc_path] = doc_length
        index.doc_titles[doc_path] = title
        index.doc_urls[doc_path] = url
        index.doc_sha256s[doc_path] = sha256_map.get(url, "")
        index.doc_count += 1
        total_length += doc_length

        # Build inverted index
        term_positions: dict[str, list[int]] = {}
        for pos, token in enumerate(tokens):
            if token not in term_positions:
                term_positions[token] = []
            term_positions[token].append(pos)

        for term, positions in term_positions.items():
            if term not in index.inverted_index:
                index.inverted_index[term] = []
            index.inverted_index[term].append(Posting(
                doc_path=doc_path,
                term_frequency=len(positions),
                positions=positions,
            ))

    if index.doc_count > 0:
        index.avg_doc_length = total_length / index.doc_count

    # Save index metadata
    meta_path = os.path.join(cache_dir, "_search_index.json")
    with open(meta_path, "w") as f:
        json.dump({
            "doc_count": index.doc_count,
            "avg_doc_length": index.avg_doc_length,
            "terms_count": len(index.inverted_index),
        }, f, indent=2)

    return index


def _bm25_score(
    term_freq: int,
    doc_length: int,
    avg_doc_length: float,
    doc_freq: int,
    total_docs: int,
) -> float:
    """Compute BM25 score for a single term in a single document."""
    if total_docs == 0 or doc_freq == 0:
        return 0.0
    idf = math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)
    tf = (term_freq * (K1 + 1)) / (term_freq + K1 * (1 - B + B * doc_length / avg_doc_length))
    return idf * tf


def _extract_snippets(content: str, query_tokens: set[str], max_snippets: int = 3) -> list[str]:
    """Extract sentences containing query terms."""
    sentences = re.split(r'[.!?\n]+', content)
    scored = []
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20 or len(sent) > 500:
            continue
        sent_tokens = set(tokenize(sent))
        overlap = len(sent_tokens & query_tokens)
        if overlap > 0:
            scored.append((overlap, sent))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:max_snippets]]


def search(query: str, index: SearchIndex, cache_dir: str, top_k: int = 10) -> list[SearchResult]:
    """Search the index using BM25 scoring."""
    query_tokens = tokenize(query)
    if not query_tokens or index.doc_count == 0:
        return []

    # Score each document
    scores: dict[str, float] = {}
    for token in query_tokens:
        postings = index.inverted_index.get(token, [])
        doc_freq = len(postings)
        for posting in postings:
            score = _bm25_score(
                posting.term_frequency,
                index.doc_lengths[posting.doc_path],
                index.avg_doc_length,
                doc_freq,
                index.doc_count,
            )
            scores[posting.doc_path] = scores.get(posting.doc_path, 0) + score

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    # Build results with snippets
    results = []
    pages_dir = os.path.join(cache_dir, "pages")
    query_token_set = set(query_tokens)

    for doc_path, score in ranked:
        # Read content for snippets
        filepath = os.path.join(pages_dir, doc_path)
        snippets = []
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                content = f.read()
            snippets = _extract_snippets(content, query_token_set)

        results.append(SearchResult(
            url=index.doc_urls.get(doc_path, ""),
            path=doc_path.replace("__", "/").replace(".md", ""),
            title=index.doc_titles.get(doc_path, ""),
            score=round(score, 4),
            snippets=snippets,
            doc_sha256=index.doc_sha256s.get(doc_path, ""),
        ))

    return results


def get_citation_url(path: str) -> str:
    """Convert a doc path to a full citation URL."""
    path = path.replace("__", "/").replace(".md", "")
    return f"https://www.revenuecat.com/docs/{path}"


def format_citations(results: list[SearchResult]) -> str:
    """Format search results as a markdown citation block."""
    if not results:
        return ""
    lines = ["## Sources", ""]
    for r in results:
        lines.append(f"- [{r.title}]({r.url})")
    return "\n".join(lines)


def hybrid_search(query: str, cache_dir: str, db_conn=None, top_k: int = 10) -> list[SearchResult]:
    """Hybrid BM25 + semantic search. Builds both indexes if needed.

    This is the recommended search function for all RAG use cases.
    Falls back to BM25-only if RAG index fails to build.
    """
    bm25_index = build_index(cache_dir, db_conn)

    try:
        from .rag import build_rag_index, hybrid_search as _hybrid
        rag_index = build_rag_index(cache_dir, db_conn)
        if rag_index.chunks:
            return _hybrid(query, rag_index, bm25_index, cache_dir, top_k=top_k)
    except Exception:
        pass

    # Fall back to BM25
    return search(query, bm25_index, cache_dir, top_k=top_k)
