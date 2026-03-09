FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .

EXPOSE 8080

# Search-only API server: BM25 from cached .md files + ChromaDB Cloud vectors + HF reranker
# .docs_cache/pages/ (326 doc pages) is in the repo
# Secrets (HF_TOKEN, CHROMA_*, TURSO_*) set via Render env vars at runtime
CMD ["python3", "-m", "cli", "search-api", "--host", "0.0.0.0", "--port", "8080"]
