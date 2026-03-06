"""HTTP API server: lets other systems talk to the advocate agent."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from ..config import Config
from .chat import AdvocateAgent


class AgentHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests to the advocate agent API."""

    agent: AdvocateAgent = None  # Set by serve()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._json_response({"status": "ok", "agent": "RevenueCat Advocate OS"})

        elif parsed.path == "/stats":
            stats = self.agent.get_stats()
            self._json_response(stats)

        elif parsed.path == "/suggest":
            topics = self.agent.suggest_topics()
            self._json_response({"suggestions": topics})

        else:
            self._json_response({"error": "Not found", "endpoints": [
                "GET /health", "GET /stats", "GET /suggest",
                "POST /ask", "POST /search",
            ]}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_body()

        if parsed.path == "/ask":
            question = body.get("question", "")
            if not question:
                self._json_response({"error": "Missing 'question' field"}, status=400)
                return

            response = self.agent.ask(question)
            self._json_response({
                "question": question,
                "response": response,
            })

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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # Quieter logging
        pass


def serve(config: Config, host: str = "0.0.0.0", port: int = 8080):
    """Start the agent API server."""
    agent = AdvocateAgent(config)
    AgentHandler.agent = agent

    server = HTTPServer((host, port), AgentHandler)
    print(f"Advocate Agent API running at http://{host}:{port}")
    print(f"Endpoints:")
    print(f"  GET  /health    Health check")
    print(f"  GET  /stats     Agent statistics")
    print(f"  GET  /suggest   Suggested questions")
    print(f"  POST /ask       Ask a question (JSON: {{\"question\": \"...\"}})")
    print(f"  POST /search    Search docs (JSON: {{\"query\": \"...\", \"top_k\": 5}})")
    print(f"\nPress Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
