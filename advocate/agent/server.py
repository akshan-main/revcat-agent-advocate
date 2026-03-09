"""HTTP API server: lets other systems talk to the advocate agent.

Modes:
  Full mode (default):  All endpoints, requires full config + AdvocateAgent.
  Search-only mode:     Only /api/search — lightweight, designed for Fly.io deployment.
                        Serves hybrid RAG search (BM25 + ChromaDB + HF reranker).
                        Client-side JS calls this, gets doc chunks, sends to Anthropic
                        with user's own key. No LLM cost on server side.

WARNING: This server has no authentication. Only bind to localhost (127.0.0.1)
unless you add your own auth layer or deploy behind a CDN/proxy.
"""
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from ..config import Config

logger = logging.getLogger(__name__)

# Allowed origins for CORS (GitHub Pages + localhost dev)
ALLOWED_ORIGINS = {
    "https://akshankrithick.github.io",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
}


class AgentHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests to the advocate agent API."""

    agent = None          # Set by serve() — full mode only
    search_index = None   # BM25 index — set by serve() or serve_search_only()
    rag_index = None      # ChromaDB RAG index — set by serve_search_only()
    cache_dir = ""        # Docs cache directory
    db_conn = None        # DB connection for search

    def _cors_headers(self):
        """Add CORS headers for cross-origin requests from GitHub Pages."""
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._json_response({"status": "ok", "agent": "revcat-agent-advocate"})

        elif parsed.path == "/api/search":
            self._handle_search_get(qs)

        elif self.agent and parsed.path == "/stats":
            stats = self.agent.get_stats()
            self._json_response(stats)

        elif self.agent and parsed.path == "/suggest":
            topics = self.agent.suggest_topics()
            self._json_response({"suggestions": topics})

        else:
            endpoints = ["GET /health", "GET /api/search?q=...&top_k=8"]
            if self.agent:
                endpoints.extend([
                    "GET /stats", "GET /suggest",
                    "POST /ask", "POST /search",
                ])
            self._json_response({"error": "Not found", "endpoints": endpoints}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_body()

        if parsed.path == "/api/search":
            query = body.get("q", body.get("query", ""))
            top_k = body.get("top_k", 8)
            self._do_hybrid_search(query, int(top_k))
            return

        if not self.agent:
            self._json_response({"error": "Search-only mode. Use GET /api/search?q=..."}, status=404)
            return

        if parsed.path == "/ask":
            question = body.get("question", "")
            if not question:
                self._json_response({"error": "Missing 'question' field"}, status=400)
                return
            response = self.agent.ask(question)
            self._json_response({"question": question, "response": response})

        elif parsed.path == "/search":
            query = body.get("query", "")
            top_k = body.get("top_k", 5)
            if not query:
                self._json_response({"error": "Missing 'query' field"}, status=400)
                return
            from ..knowledge.search import search
            self.agent._ensure_index()
            results = search(query, self.agent.index, self.agent.config.docs_cache_dir, top_k=top_k)
            self._json_response({
                "query": query,
                "results": [
                    {"title": r.title, "url": r.url, "score": r.score, "snippets": r.snippets}
                    for r in results
                ],
            })
        else:
            self._json_response({"error": "Not found"}, status=404)

    def _handle_search_get(self, qs: dict):
        """Handle GET /api/search?q=...&top_k=8"""
        query = qs.get("q", [""])[0]
        top_k = int(qs.get("top_k", ["8"])[0])
        self._do_hybrid_search(query, top_k)

    def _do_hybrid_search(self, query: str, top_k: int = 8):
        """Run hybrid search (BM25 + ChromaDB vectors + HF reranker) and return chunks."""
        if not query:
            self._json_response({"error": "Missing 'q' parameter"}, status=400)
            return

        top_k = min(max(top_k, 1), 20)  # Clamp 1-20

        try:
            results = []

            # Try hybrid search (vector + BM25 + reranker) first
            if self.rag_index and self.rag_index.chunks:
                from ..knowledge.rag import hybrid_search as rag_hybrid
                results = rag_hybrid(
                    query, self.rag_index,
                    bm25_index=self.search_index,
                    cache_dir=self.cache_dir,
                    top_k=top_k,
                )
            elif self.search_index:
                # Fallback to BM25 only
                from ..knowledge.search import search as bm25_search
                results = bm25_search(query, self.search_index, self.cache_dir, top_k=top_k)
            elif self.agent:
                # Fallback to agent's search
                from ..knowledge.search import search as bm25_search
                self.agent._ensure_index()
                results = bm25_search(query, self.agent.index, self.agent.config.docs_cache_dir, top_k=top_k)

            self._json_response({
                "query": query,
                "results": [
                    {
                        "title": r.title,
                        "url": r.url,
                        "score": r.score,
                        "snippets": r.snippets,
                        "doc_sha256": r.doc_sha256,
                    }
                    for r in results
                ],
            })
        except Exception as e:
            logger.exception("Search error")
            self._json_response({"error": f"Search failed: {str(e)}"}, status=500)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def log_message(self, format, *args):
        pass


def serve(config: Config, host: str = "127.0.0.1", port: int = 8080):
    """Start the full agent API server. Binds to localhost only (no auth)."""
    from .chat import AdvocateAgent
    agent = AdvocateAgent(config)
    AgentHandler.agent = agent
    AgentHandler.cache_dir = config.docs_cache_dir

    if host == "0.0.0.0":
        print("WARNING: Binding to 0.0.0.0 exposes this unauthenticated server to the network.")
        print("         Use --host 127.0.0.1 (default) for local-only access.")

    server = HTTPServer((host, port), AgentHandler)
    print(f"Advocate Agent API running at http://{host}:{port}")
    print("Endpoints:")
    print("  GET  /health              Health check")
    print("  GET  /api/search?q=...    Hybrid RAG search (BM25 + vectors + reranker)")
    print("  GET  /stats               Agent statistics")
    print("  GET  /suggest             Suggested questions")
    print("  POST /ask                 Ask a question")
    print("  POST /search              Search docs (legacy)")
    print("\nPress Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


def serve_search_only(host: str = "0.0.0.0", port: int = 8080):
    """Start search-only API server for Fly.io deployment.

    Only serves /health and /api/search with hybrid RAG.
    Requires: HF_TOKEN, CHROMA_API_KEY, CHROMA_TENANT, CHROMA_DATABASE in env.
    Docs must be pre-cached in DOCS_CACHE_DIR (baked into Docker image).
    """
    config = Config()
    cache_dir = config.docs_cache_dir

    print("Search API server starting...")
    print(f"  Docs cache: {cache_dir}")

    # Build BM25 index from cached docs
    from ..knowledge.search import build_index
    db_conn = None
    try:
        from ..db import init_db_from_config
        db_conn = init_db_from_config(config)
        print("  DB: connected")
    except Exception as e:
        print(f"  DB: skipped ({e})")

    bm25_index = build_index(cache_dir, db_conn)
    print(f"  BM25 index: {bm25_index.doc_count} docs, {len(bm25_index.inverted_index)} terms")

    # Connect to existing RAG index in ChromaDB Cloud (no re-indexing)
    rag_index = None
    try:
        from ..knowledge.rag import connect_rag_index
        rag_index = connect_rag_index(
            cache_dir, db_conn,
            hf_token=config.hf_token,
            chroma_api_key=config.chroma_api_key,
            chroma_tenant=config.chroma_tenant,
            chroma_database=config.chroma_database,
        )
        print(f"  RAG index: {rag_index.doc_count} docs, {rag_index.chunk_count} chunks")
    except Exception as e:
        print(f"  RAG index: skipped ({e}), using BM25 only")

    AgentHandler.agent = None
    AgentHandler.search_index = bm25_index
    AgentHandler.rag_index = rag_index
    AgentHandler.cache_dir = cache_dir
    AgentHandler.db_conn = db_conn

    server = HTTPServer((host, port), AgentHandler)
    print(f"\nSearch API running at http://{host}:{port}")
    print("Endpoints:")
    print("  GET  /health              Health check")
    print("  GET  /api/search?q=...    Hybrid RAG search")
    print("\nPress Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
