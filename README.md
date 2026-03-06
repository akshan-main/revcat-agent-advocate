# revcat-agent-advocate

Autonomous AI agent applying for RevenueCat's Agentic AI Developer & Growth Advocate role. Ingests RevenueCat documentation, generates cited technical content, runs growth experiments, files structured product feedback, and publishes everything to a static site with a hash-chained audit trail. Every output is verifiable. Every claim has receipts.

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
cp .env.example .env  # fill in API keys
revcat-advocate ingest-docs
revcat-advocate write-content --topic "Your Topic" --type tutorial
revcat-advocate build-site
```

## What It Does

| Weekly Deliverable | Command |
|---|---|
| 2+ content pieces (tutorials, case studies, playbooks) | `write-content --topic "..." --type tutorial` |
| 1+ growth experiment | `run-experiment --name programmatic-seo` |
| 50+ community interactions | `scan-github`, `scan-reddit`, `queue-replies` |
| 3+ product feedback items | `generate-feedback --count 3` |
| Weekly report | `weekly-report` |

## All Commands

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

## Tamper-Evident Ledger

Every command creates a hash-chained log entry:

```
hash = sha256(prev_hash + canonical_json)
```

Optional HMAC signature via `LEDGER_HMAC_KEY`. Verify with `revcat-advocate verify-ledger`. Browse at `/ledger` on the published site.

## Architecture

```
Docs (LLM Index + .md mirrors)
    -> Knowledge Engine (BM25 + RAG hybrid search)
        -> Content Engine (Claude API + citation verification)
        -> Growth Engine (experiments + programmatic SEO)
        -> Feedback Engine (doc analysis + repro harness)
        -> Community (GitHub, Reddit, X, all DRY_RUN gated)
    -> Ledger (hash-chained, HMAC-signed)
        -> Static Site (GitHub Pages)
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
