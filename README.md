# RevenueCat Advocate OS

Agent system for the RevenueCat Agentic AI Developer & Growth Advocate role. Ingests RevenueCat documentation, generates cited technical content, runs growth experiments, files structured product feedback, and publishes to a static site with a hash-chained audit trail.

## Quick Start

### Demo Mode (no RevenueCat credentials needed)

```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...
export DEMO_MODE=true
revcat-advocate demo-run
python -m http.server -d site_output 8000
```

### Real Mode

```bash
pip install -e ".[dev]"
export REVENUECAT_API_KEY=sk_your_key
export REVENUECAT_PROJECT_ID=proj_your_id
export ANTHROPIC_API_KEY=sk-ant-...
export DEMO_MODE=false
revcat-advocate ingest-docs
revcat-advocate write-content --topic "Your Topic" --type tutorial
revcat-advocate build-site
```

## Commands

| Command | Description |
|---------|-------------|
| `ingest-docs [--force]` | Download RC docs index, fetch .md mirrors, build search index |
| `write-content --topic "..." --type tutorial\|case_study\|agent_playbook` | Generate content with citations and verification |
| `run-experiment --name programmatic-seo` | Start a growth experiment |
| `generate-feedback [--count N]` | Generate structured product feedback from doc analysis |
| `queue-replies --source github --questions file.json` | Draft community responses (never auto-posts) |
| `tweet [--topic "..."] [--thread --count N]` | Draft tweets about RevenueCat |
| `scan-github [--since 72] [--limit 10]` | Scan RC repos for issues, draft responses |
| `scan-reddit [--since 72] [--limit 15]` | Scan subreddits for RC-related posts, draft responses |
| `competitive-digest` | Generate competitive intelligence from public data |
| `analyze-docs` | Analyze documentation quality and coverage |
| `repro-test [--scenario name]` | Run API/MCP repro scenarios to find friction |
| `weekly-report [--with-charts]` | Generate weekly activity summary |
| `build-site` | Build static site from DB |
| `deploy [--repo owner/name]` | Deploy to GitHub Pages |
| `verify-ledger` | Verify hash chain integrity |
| `generate-application` | Generate the /apply application letter |
| `chat` | Interactive chat with doc-grounded responses |
| `serve [--port 8080]` | HTTP API server |
| `mcp-serve` | MCP server (other agents can connect) |
| `auto [--interval 6h]` | Autonomous scheduled operation |
| `demo-run` | Run full pipeline end-to-end |

## Safety Gates

| Flag | Default | Effect |
|------|---------|--------|
| `DRY_RUN` | `true` | No external posts, no GitHub issues; drafts only |
| `ALLOW_WRITES` | `false` | Blocks POST/PUT/DELETE to RevenueCat API |
| `DEMO_MODE` | `false` | Uses mock API responses, labels all output `[DEMO]` |

## Ledger

Every command creates a hash-chained log entry:

```
hash = sha256(prev_hash + canonical_json)
```

Optional HMAC signature via `LEDGER_HMAC_KEY`. Verify with `revcat-advocate verify-ledger`.

## Architecture

```
Docs (LLM Index + .md mirrors)
    -> Knowledge Engine (BM25 + RAG hybrid search)
        -> Content Engine (Claude API + citation verification)
        -> Growth Engine (experiments + programmatic SEO)
        -> Feedback Engine (doc analysis + repro harness)
        -> Social (GitHub, Reddit, X, all DRY_RUN gated)
    -> Governance (red-team suite, safety gates)
    -> Ledger (hash-chained, HMAC-signed)
        -> Static Site (GitHub Pages)
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v    # 259 tests
```

Covers: ledger tamper detection, citation verification, content pipeline, API safety gates, governance red-team, golden snapshot regression, competitive intelligence, repro harness.
