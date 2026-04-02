# revcat-agent-advocate

Agent that does RevenueCat developer advocacy. Ingests docs, writes content, tweets, scans communities, runs experiments, files feedback. All state in Turso, all actions logged to a hash-chained ledger.

**Site:** [akshan-main.github.io/revcat-agent-advocate](https://akshan-main.github.io/revcat-agent-advocate)

## What's in the box

| Thing | Count |
|-------|-------|
| Content pieces | 12 |
| Product feedback | 29 |
| Growth experiments | 2 |
| MCP tools | 22 |
| Claude Code skills | 11 |
| Tests | 314 |
| DB tables | 10 |

## Tell the agent what to do

Open an issue in this repo with the label `agent-task`. A dedicated GitHub Actions workflow triggers on the label event, injects the task as a signal, and the supervisor executes it directly — no producer ingestion, no scoring queue. The issue is closed automatically on success, left open on failure.

Examples:
- "Write a tutorial about migrating from Stripe to RevenueCat"
- "Tweet about the new Charts API"
- "Apply to the RevenueCat job at [URL]" (uses Playwright MCP to fill forms)

## Supervisor

Event-driven loop running every 6 hours via GitHub Actions (containerized, non-root, read-only FS).

```
OBSERVE — ingest signals (GitHub issues, Reddit, Dev.to stats, doc changes, scheduled tasks)
DECIDE  — score by impact*urgency*confidence*freshness, claim top signal
ACT     — execute through firewall + rate limits
LEARN   — record outcome, update Thompson sampling bandit
```

Scheduled runs: `max_actions=1`. Manual dispatch: up to 3.

## MCP Server

22 tools via FastMCP. Any MCP client can connect:

```bash
claude mcp add rcagent -- python3 -m cli mcp-serve --transport stdio
```

## Architecture

```
RevenueCat Docs (LLM Index + .md mirrors)
    -> Hybrid RAG (BM25 + ChromaDB vectors + Contextual AI reranker)
        -> Content Engine (Claude + citation verification)
        -> Growth Engine (experiments + SEO)
        -> Feedback Engine (doc analysis)
        -> Social (Dev.to + Twitter + GitHub/Reddit scanning)
    -> Supervisor (signal-driven OODA loop, 6-hour cycles)
        -> Signal Pipeline (5 producers: GitHub, Reddit, Dev.to, docs, schedule)
        -> Thompson Sampling Bandit (10 topic categories, Beta priors)
        -> Playwright MCP Browser (enrichment + form submission)
        -> Action Firewall (YAML rules + rate limits + eval gates)
    -> Turso (10-table cloud DB, all state)
    -> Ledger (SHA256 hash chain + optional HMAC signing)
    -> Agent Memory (lessons + pruning policies)
    -> MCP Server (22 tools + 3 resources via FastMCP)
        -> Static Site (GitHub Pages)
```

| Layer | Tech |
|-------|------|
| DB | Turso (cloud libsql) |
| Vectors | ChromaDB Cloud |
| Embeddings | HF Inference API (`all-mpnet-base-v2`) |
| Reranker | Contextual AI v2 |
| LLM | Claude API |
| Publishing | Dev.to Forem API |
| CI | GitHub Actions |
| Browser | Playwright MCP |
| Site | GitHub Pages |

## Quick Start

```bash
pip install -e ".[dev]"
cp .env.example .env  # fill in keys
revcat-advocate ingest-docs
revcat-advocate write-content --topic "Your Topic" --type tutorial
revcat-advocate build-site
```

Demo mode (no external creds):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export DEMO_MODE=true
revcat-advocate demo-run
```

## Commands

| Command | What it does |
|---------|-------------|
| `ingest-docs` | Fetch RC docs, build search index |
| `write-content --topic "..."` | Generate content with citations |
| `run-experiment --name programmatic-seo` | Growth experiment |
| `generate-feedback` | Product feedback from doc analysis |
| `tweet --topic "..."` | Draft/post tweets |
| `supervise` | Run supervisor cycle |
| `supervise --daemon --interval 21600` | Continuous supervisor (6-hour cycles) |
| `scan-github` | Scan RC repos for issues |
| `scan-reddit` | Scan subreddits |
| `publish-devto` | Publish to Dev.to |
| `build-site` | Build static site |
| `deploy` | Deploy to GitHub Pages |
| `verify-ledger` | Check hash chain integrity |
| `mcp-serve` | Start MCP server |
| `agent --goal "..."` | Autonomous agent loop |
| `prune-memory` | Prune stale/duplicate agent memory |
| `devto-stats` | Sync Dev.to engagement stats |
| `chat` | Interactive Q&A |

## Safety

| Flag | Default | Effect |
|------|---------|--------|
| `DRY_RUN` | `true` | Drafts only, no external posts |
| `ALLOW_WRITES` | `false` | Read-only API access |
| `DEMO_MODE` | `false` | Mock API responses |

Firewall rate limits: max 2 content/day, 3 tweets/day, 5 responses/day.

## RAG

Hybrid BM25 + semantic retrieval with reranking.

| Metric | Score |
|--------|-------|
| MRR@5 | 0.900 |
| Recall@5 | 91.7% |
| Hit Rate@3 | 100% |

## Dev

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
