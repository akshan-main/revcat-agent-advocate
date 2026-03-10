"""RAG Pipeline: Retrieval Augmented Generation.

Stack:
- ChromaDB Cloud: hosted vector database (free 10GB tier)
- Hugging Face Inference API: remote embeddings (all-mpnet-base-v2, 768-dim)
- Hugging Face Inference API: remote reranker (cross-encoder/ms-marco-MiniLM-L-12-v2)
- BM25: keyword search for exact matches (existing module)
- Hybrid scoring: combine vector similarity + BM25 + reranker scores

Cloud-hosted by default; falls back to local ChromaDB if cloud credentials not configured.
"""
import json
import os
import re
from dataclasses import dataclass, field

try:
    import chromadb
    from chromadb import EmbeddingFunction, Documents, Embeddings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    Documents = list
    Embeddings = list
    EmbeddingFunction = object

from ..models import SearchResult

# Chunking config
MIN_CHUNK_WORDS = 15
MAX_CHUNK_WORDS = 500

# HF Inference config
HF_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
HF_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"


class HuggingFaceInferenceEmbedding(EmbeddingFunction):
    """Embedding function that calls HF Inference API; no local model download."""

    def __init__(self, api_key: str | None = None, model: str = HF_EMBEDDING_MODEL):
        from huggingface_hub import InferenceClient
        self._client = InferenceClient(model=model, token=api_key)
        self._model = model

    def name(self) -> str:
        return f"hf-inference:{self._model}"

    def __call__(self, input: Documents) -> Embeddings:
        # HF InferenceClient.feature_extraction returns embeddings
        results = []
        # Batch to avoid timeouts on large inputs
        batch_size = 32
        for i in range(0, len(input), batch_size):
            batch = input[i:i + batch_size]
            embeddings = self._client.feature_extraction(batch)
            # Returns list of lists of floats (or numpy arrays)
            for emb in embeddings:
                if hasattr(emb, 'tolist'):
                    emb = emb.tolist()
                # Handle nested arrays: feature_extraction returns token-level embeddings
                # We need sentence-level, so mean-pool if needed
                if emb and isinstance(emb[0], list):
                    # Mean pool across tokens
                    n_tokens = len(emb)
                    dim = len(emb[0])
                    pooled = [sum(emb[t][d] for t in range(n_tokens)) / n_tokens for d in range(dim)]
                    results.append(pooled)
                else:
                    results.append(emb)
        return results


@dataclass
class Chunk:
    """A section of a documentation page."""
    doc_path: str
    doc_url: str
    doc_title: str
    doc_sha256: str
    heading: str
    text: str
    word_count: int
    chunk_index: int


@dataclass
class RAGIndex:
    """Wrapper around ChromaDB collection + metadata."""
    collection: object = None  # chromadb Collection
    chunks: list[Chunk] = field(default_factory=list)
    doc_count: int = 0
    chunk_count: int = 0


def _extract_title(content: str) -> str:
    for line in content.splitlines()[:20]:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _path_to_url(path: str) -> str:
    doc_path = path.replace("__", "/")
    if doc_path.endswith(".md"):
        doc_path = doc_path[:-3]
    return f"https://www.revenuecat.com/docs/{doc_path}"


def _split_by_headings(content: str) -> list[tuple[str, str]]:
    """Split markdown content by heading boundaries."""
    sections = []
    current_heading = "Introduction"
    current_lines = []

    for line in content.splitlines():
        if re.match(r'^#{1,4}\s+', line):
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append((current_heading, text))
            current_heading = re.sub(r'^#+\s+', '', line).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append((current_heading, text))

    return sections


def _split_long_section(text: str) -> list[str]:
    """Split a long section at paragraph boundaries."""
    paragraphs = re.split(r'\n\s*\n', text)
    sub_chunks = []
    current = []
    current_words = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_words + para_words > MAX_CHUNK_WORDS and current:
            sub_chunks.append("\n\n".join(current))
            current = [para]
            current_words = para_words
        else:
            current.append(para)
            current_words += para_words

    if current:
        sub_chunks.append("\n\n".join(current))

    return sub_chunks


def chunk_document(content: str, doc_path: str, doc_url: str,
                   doc_title: str, doc_sha256: str) -> list[Chunk]:
    """Split a document into chunks by markdown headings."""
    chunks = []
    sections = _split_by_headings(content)

    for heading, text in sections:
        words = text.split()
        word_count = len(words)

        if word_count < MIN_CHUNK_WORDS:
            if chunks:
                prev = chunks[-1]
                merged = prev.text + "\n\n" + text
                chunks[-1] = Chunk(
                    doc_path=doc_path, doc_url=doc_url,
                    doc_title=doc_title, doc_sha256=doc_sha256,
                    heading=prev.heading, text=merged,
                    word_count=len(merged.split()),
                    chunk_index=prev.chunk_index,
                )
            else:
                chunks.append(Chunk(
                    doc_path=doc_path, doc_url=doc_url,
                    doc_title=doc_title, doc_sha256=doc_sha256,
                    heading=heading, text=text,
                    word_count=word_count, chunk_index=0,
                ))
            continue

        if word_count > MAX_CHUNK_WORDS:
            for sub_text in _split_long_section(text):
                chunks.append(Chunk(
                    doc_path=doc_path, doc_url=doc_url,
                    doc_title=doc_title, doc_sha256=doc_sha256,
                    heading=heading, text=sub_text,
                    word_count=len(sub_text.split()),
                    chunk_index=len(chunks),
                ))
        else:
            chunks.append(Chunk(
                doc_path=doc_path, doc_url=doc_url,
                doc_title=doc_title, doc_sha256=doc_sha256,
                heading=heading, text=text,
                word_count=word_count, chunk_index=len(chunks),
            ))

    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i

    return chunks


def _get_embedding_function(api_key: str | None = None) -> HuggingFaceInferenceEmbedding:
    """Create the HF Inference API embedding function."""
    return HuggingFaceInferenceEmbedding(api_key=api_key, model=HF_EMBEDDING_MODEL)


def _get_chroma_client(cache_dir: str,
                       chroma_api_key: str | None = None,
                       chroma_tenant: str | None = None,
                       chroma_database: str | None = None):
    """Get ChromaDB client: cloud if credentials provided, otherwise local fallback."""
    if not HAS_CHROMADB:
        return None
    if chroma_api_key:
        return chromadb.CloudClient(
            tenant=chroma_tenant or "default_tenant",
            database=chroma_database or "default_database",
            api_key=chroma_api_key,
        )
    # Local fallback for tests
    chroma_dir = os.path.join(cache_dir, "_chroma")
    return chromadb.PersistentClient(path=chroma_dir)


def build_rag_index(cache_dir: str, db_conn=None, hf_token: str | None = None,
                    chroma_api_key: str | None = None,
                    chroma_tenant: str | None = None,
                    chroma_database: str | None = None) -> RAGIndex:
    """Build ChromaDB vector index from cached doc pages.

    Uses ChromaDB Cloud + HF Inference API if configured.
    Falls back to local ChromaDB if cloud credentials not provided.
    """
    if not HAS_CHROMADB:
        return RAGIndex()

    pages_dir = os.path.join(cache_dir, "pages")
    if not os.path.isdir(pages_dir):
        return RAGIndex()

    # Get sha256 mappings from DB
    sha256_map = {}
    if db_conn:
        try:
            rows = db_conn.execute("SELECT url, doc_sha256 FROM doc_snapshots").fetchall()
            for row in rows:
                if isinstance(row, dict):
                    sha256_map[row["url"]] = row["doc_sha256"]
                else:
                    sha256_map[row[0]] = row[1]
        except Exception:
            pass

    # Chunk all documents
    all_chunks = []
    doc_count = 0

    for filename in sorted(os.listdir(pages_dir)):
        if not filename.endswith(".md"):
            continue

        filepath = os.path.join(pages_dir, filename)
        with open(filepath, "r") as f:
            content = f.read()

        doc_url = _path_to_url(filename)
        doc_title = _extract_title(content) or filename.replace("__", "/").replace(".md", "")
        doc_sha256 = sha256_map.get(doc_url, "")

        chunks = chunk_document(content, filename, doc_url, doc_title, doc_sha256)
        all_chunks.extend(chunks)
        doc_count += 1

    if not all_chunks:
        return RAGIndex()

    # Resolve credentials from env if not passed
    if hf_token is None:
        hf_token = os.environ.get("HF_TOKEN")
    if chroma_api_key is None:
        chroma_api_key = os.environ.get("CHROMA_API_KEY")
    if chroma_tenant is None:
        chroma_tenant = os.environ.get("CHROMA_TENANT")
    if chroma_database is None:
        chroma_database = os.environ.get("CHROMA_DATABASE")

    client = _get_chroma_client(cache_dir, chroma_api_key, chroma_tenant, chroma_database)
    embedding_fn = _get_embedding_function(api_key=hf_token)

    # Get or create collection (avoids ChromaDB Cloud soft-delete grace period issues)
    collection = client.get_or_create_collection(
        name="revenuecat_docs",
        metadata={"hnsw:space": "cosine"},
        embedding_function=embedding_fn,
    )

    # Clear existing data for a fresh rebuild
    try:
        existing_ids = collection.get()["ids"]
        if existing_ids:
            for i in range(0, len(existing_ids), 500):
                collection.delete(ids=existing_ids[i:i + 500])
    except Exception:
        pass

    # Add chunks in batches, truncating any that exceed ChromaDB's limit
    max_doc_bytes = 15000  # ChromaDB Cloud free tier limit is 16384 bytes
    batch_size = 32
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        collection.add(
            documents=[c.text[:max_doc_bytes] for c in batch],
            metadatas=[{
                "doc_path": c.doc_path,
                "doc_url": c.doc_url,
                "doc_title": c.doc_title,
                "doc_sha256": c.doc_sha256,
                "heading": c.heading,
                "word_count": c.word_count,
            } for c in batch],
            ids=[f"chunk_{i + j}" for j in range(len(batch))],
        )

    index = RAGIndex(
        collection=collection,
        chunks=all_chunks,
        doc_count=doc_count,
        chunk_count=len(all_chunks),
    )

    # Save metadata
    meta_path = os.path.join(cache_dir, "_rag_index.json")
    with open(meta_path, "w") as f:
        json.dump({
            "doc_count": index.doc_count,
            "chunk_count": index.chunk_count,
            "embedding_model": f"hf-inference:{HF_EMBEDDING_MODEL}",
            "vector_db": "chromadb-cloud" if chroma_api_key else "chromadb-local",
            "reranker": f"hf-inference:{HF_RERANKER_MODEL}",
        }, f, indent=2)

    return index


def connect_rag_index(cache_dir: str, db_conn=None, hf_token: str | None = None,
                      chroma_api_key: str | None = None,
                      chroma_tenant: str | None = None,
                      chroma_database: str | None = None) -> RAGIndex:
    """Connect to an existing ChromaDB collection without re-indexing.

    Use this for read-only search servers (e.g. Fly.io) that should use the
    already-indexed vectors in ChromaDB Cloud rather than rebuilding.
    Falls back to build_rag_index if the collection doesn't exist.
    """
    if not HAS_CHROMADB:
        return RAGIndex()

    # Resolve credentials from env if not passed
    if hf_token is None:
        hf_token = os.environ.get("HF_TOKEN")
    if chroma_api_key is None:
        chroma_api_key = os.environ.get("CHROMA_API_KEY")
    if chroma_tenant is None:
        chroma_tenant = os.environ.get("CHROMA_TENANT")
    if chroma_database is None:
        chroma_database = os.environ.get("CHROMA_DATABASE")

    client = _get_chroma_client(cache_dir, chroma_api_key, chroma_tenant, chroma_database)
    embedding_fn = _get_embedding_function(api_key=hf_token)

    try:
        collection = client.get_or_create_collection(
            name="revenuecat_docs",
            metadata={"hnsw:space": "cosine"},
            embedding_function=embedding_fn,
        )
        count = collection.count()
        if count == 0:
            raise ValueError("Collection empty")
    except Exception:
        # Collection doesn't exist or is empty — fall back to full build
        return build_rag_index(cache_dir, db_conn, hf_token,
                               chroma_api_key, chroma_tenant, chroma_database)

    # Build local chunk metadata from cached docs (for snippet extraction)
    pages_dir = os.path.join(cache_dir, "pages")
    all_chunks = []
    doc_count = 0

    sha256_map = {}
    if db_conn:
        try:
            rows = db_conn.execute("SELECT url, doc_sha256 FROM doc_snapshots").fetchall()
            for row in rows:
                if isinstance(row, dict):
                    sha256_map[row["url"]] = row["doc_sha256"]
                else:
                    sha256_map[row[0]] = row[1]
        except Exception:
            pass

    if os.path.isdir(pages_dir):
        for filename in sorted(os.listdir(pages_dir)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(pages_dir, filename)
            with open(filepath, "r") as f:
                content = f.read()
            doc_url = _path_to_url(filename)
            doc_title = _extract_title(content) or filename.replace("__", "/").replace(".md", "")
            doc_sha256 = sha256_map.get(doc_url, "")
            chunks = chunk_document(content, filename, doc_url, doc_title, doc_sha256)
            all_chunks.extend(chunks)
            doc_count += 1

    return RAGIndex(
        collection=collection,
        chunks=all_chunks,
        doc_count=doc_count,
        chunk_count=len(all_chunks),
    )


def connect_rag_index_from_config(config, db_conn=None) -> RAGIndex:
    """Connect to existing RAG index using config object."""
    return connect_rag_index(
        config.docs_cache_dir,
        db_conn=db_conn,
        hf_token=config.hf_token,
        chroma_api_key=config.chroma_api_key,
        chroma_tenant=config.chroma_tenant,
        chroma_database=config.chroma_database,
    )


def build_rag_index_from_config(config, db_conn=None) -> RAGIndex:
    """Build RAG index using config object; picks cloud or local automatically."""
    return build_rag_index(
        config.docs_cache_dir,
        db_conn=db_conn,
        hf_token=config.hf_token,
        chroma_api_key=config.chroma_api_key,
        chroma_tenant=config.chroma_tenant,
        chroma_database=config.chroma_database,
    )


def _rerank_hf(query: str, candidates: list[tuple[Chunk, float]],
               top_k: int, hf_token: str | None = None) -> list[tuple[Chunk, float]]:
    """Rerank candidates using HF Inference API cross-encoder."""
    if len(candidates) <= 1:
        return candidates

    try:
        from huggingface_hub import InferenceClient
        if hf_token is None:
            hf_token = os.environ.get("HF_TOKEN")

        client = InferenceClient(token=hf_token)

        # Score each candidate against the query using the cross-encoder
        scored = []
        for chunk, vector_score in candidates:
            # Cross-encoder takes (query, passage) pairs
            result = client.text_classification(
                {"text": query, "text_pair": chunk.text},
                model=HF_RERANKER_MODEL,
            )
            # Result is list of {label, score}; cross-encoders return a relevance score
            if result and len(result) > 0:
                rerank_score = result[0].score if hasattr(result[0], 'score') else 0.0
            else:
                rerank_score = 0.0

            # Blend: 60% reranker + 40% vector similarity
            combined = 0.6 * rerank_score + 0.4 * vector_score
            scored.append((chunk, combined))

        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    except Exception:
        return candidates


def semantic_search(query: str, index: RAGIndex, top_k: int = 10) -> list[tuple[Chunk, float]]:
    """Search using ChromaDB vector similarity."""
    if not index.collection or not index.chunks:
        return []

    results = index.collection.query(
        query_texts=[query],
        n_results=min(top_k * 2, index.chunk_count),
    )

    if not results or not results["ids"] or not results["ids"][0]:
        return []

    scored = []
    ids = results["ids"][0]
    distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)

    for id_str, distance in zip(ids, distances):
        similarity = 1.0 - distance
        idx = int(id_str.split("_")[1])
        if idx < len(index.chunks):
            scored.append((index.chunks[idx], similarity))

    # Rerank with HF cross-encoder
    scored = _rerank_hf(query, scored, top_k)

    return scored[:top_k]


def hybrid_search(
    query: str,
    rag_index: RAGIndex,
    bm25_index=None,
    cache_dir: str = "",
    top_k: int = 10,
    bm25_weight: float = 0.3,
    semantic_weight: float = 0.7,
) -> list[SearchResult]:
    """Combine BM25 keyword + ChromaDB vector + HF reranker.

    Three-stage pipeline:
    1. Vector search (ChromaDB + HF Inference all-mpnet-base-v2): semantic similarity
    2. BM25 search: exact keyword matches
    3. Reranking (HF Inference cross-encoder): precision boost
    4. Score fusion: weighted combination
    """
    if not rag_index.chunks:
        return []

    semantic_results = semantic_search(query, rag_index, top_k=top_k * 2)

    bm25_scores: dict[str, float] = {}
    if bm25_index and cache_dir:
        from .search import search as bm25_search
        bm25_results = bm25_search(query, bm25_index, cache_dir, top_k=top_k * 2)
        if bm25_results:
            max_bm25 = max(r.score for r in bm25_results) or 1.0
            for r in bm25_results:
                bm25_scores[r.url] = r.score / max_bm25

    max_semantic = max((s for _, s in semantic_results), default=1.0) or 1.0
    doc_scores: dict[str, float] = {}
    doc_chunks: dict[str, list[tuple[Chunk, float]]] = {}

    for chunk, sim in semantic_results:
        url = chunk.doc_url
        norm_sim = sim / max_semantic
        bm25_score = bm25_scores.get(url, 0.0)
        combined = semantic_weight * norm_sim + bm25_weight * bm25_score

        if url not in doc_scores or combined > doc_scores[url]:
            doc_scores[url] = combined
        if url not in doc_chunks:
            doc_chunks[url] = []
        doc_chunks[url].append((chunk, sim))

    for url, score in bm25_scores.items():
        if url not in doc_scores:
            doc_scores[url] = bm25_weight * score

    ranked = sorted(doc_scores.items(), key=lambda x: -x[1])[:top_k]

    results = []
    for url, score in ranked:
        chunks = doc_chunks.get(url, [])
        chunks.sort(key=lambda x: -x[1])

        snippets = []
        for chunk, _ in chunks[:3]:
            sentences = re.split(r'[.!?\n]+', chunk.text)
            for sent in sentences[:2]:
                sent = sent.strip()
                if len(sent) > 20:
                    snippets.append(sent)
                    break

        if chunks:
            first = chunks[0][0]
            title = first.doc_title
            path = first.doc_path.replace("__", "/").replace(".md", "")
            doc_sha256 = first.doc_sha256
        else:
            title = url.split("/")[-1]
            path = url.replace("https://www.revenuecat.com/docs/", "")
            doc_sha256 = ""

        results.append(SearchResult(
            url=url, path=path, title=title,
            score=round(score, 4),
            snippets=snippets, doc_sha256=doc_sha256,
        ))

    return results


def get_context_chunks(
    query: str,
    rag_index: RAGIndex,
    max_chunks: int = 8,
    max_words: int = 3000,
) -> list[Chunk]:
    """Get the most relevant chunks for a query, within a token budget."""
    results = semantic_search(query, rag_index, top_k=max_chunks * 2)

    selected = []
    total_words = 0

    for chunk, score in results:
        if total_words + chunk.word_count > max_words:
            continue
        selected.append(chunk)
        total_words += chunk.word_count
        if len(selected) >= max_chunks:
            break

    return selected


def format_context(chunks: list[Chunk]) -> str:
    """Format chunks as context for LLM consumption."""
    if not chunks:
        return ""

    parts = []
    for chunk in chunks:
        parts.append(
            f"--- Source: {chunk.doc_url} ({chunk.doc_title}) ---\n"
            f"Section: {chunk.heading}\n\n"
            f"{chunk.text}\n"
        )

    return "\n".join(parts)
