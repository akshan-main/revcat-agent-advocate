# RevenueCat Agent Advocate

This is an autonomous AI agent system that acts as a Developer & Growth Advocate for RevenueCat. It ingests documentation, generates cited content, runs growth experiments, files product feedback, posts to Twitter, scans communities, and logs key actions in a tamper-evident hash-chained audit trail.

## Architecture

- **Knowledge Engine** — RevenueCat doc pages ingested via LLM index + .md mirrors, searchable via hybrid BM25 + vector RAG
- **Content Engine** — Generates technical articles with doc-grounded citations and automated verification
- **Growth Engine** — Runs experiments (SEO, content series, community blitz, integration showcase)
- **Feedback Engine** — Analyzes docs for inconsistencies, files structured feedback with repro steps
- **Twitter Agent** — Drafts and posts developer tweets with critic-agent quality gate
- **Community Scanner** — Monitors GitHub repos and Reddit for developer signals
- **Ledger** — SHA256 hash-chained, HMAC-signed tamper-evident audit trail
- **MCP Server** — 22 tools via FastMCP, tested with Claude Desktop and Claude Code
- **Static Site** — Jinja2 templates -> GitHub Pages with all evidence rendered

## Key Commands

```bash
# Core pipeline
python3 -m cli ingest-docs          # Fetch and index RevenueCat docs
python3 -m cli write-content --topic "..." --type tutorial
python3 -m cli run-experiment --name programmatic-seo
python3 -m cli generate-feedback --count 3
python3 -m cli tweet --topic "..." --post
python3 -m cli scan-github --limit 10
python3 -m cli scan-reddit --limit 10

# Agent modes
python3 -m cli agent --goal "..." --max-turns 3   # Autonomous agent cycle
python3 -m cli auto --agentic --once               # Full autonomous iteration
python3 -m cli chat                                 # Interactive Q&A mode

# Infrastructure
python3 -m cli build-site            # Build static site
python3 -m cli deploy                # Deploy to GitHub Pages
python3 -m cli verify-ledger         # Verify hash chain integrity
python3 -m cli mcp-serve             # Start MCP server
python3 -m cli serve --port 8080     # Start HTTP API server
```

## Safety Gates

- `DRY_RUN=true` (default) — No external posts, drafts only
- `ALLOW_WRITES=false` (default) — Read-only API access
- `DEMO_MODE=false` — Set true for mock API responses
- Key actions logged to tamper-evident ledger
- Tweet critic agent enforces quality before posting

## Claude Code Skills

This project ships developer-facing skills as Claude Code slash commands. Each skill combines the agent's ingested doc knowledge base with the user's actual codebase:

- `/review-rc` — Review code for RevenueCat integration issues against live docs
- `/migrate` — Analyze codebase, generate migration plan from StoreKit/Stripe/Adapty/Qonversion to RevenueCat
- `/paywall` — Generate production-ready paywall UI code matched to the user's platform and design system
- `/debug-webhook` — Paste a webhook payload, get plain-English lifecycle explanation + handler code
- `/rc-audit` — Full integration audit: SDK config, entitlements, error handling, store compliance, security (scored 0-80)
- `/pricing-strategy` — Pricing optimization based on category benchmarks, trial analysis, A/B test plan

Skills are at `.claude/skills/*/SKILL.md`. Each skill searches the doc corpus via:
```python
from advocate.knowledge.search import build_index, search
```

## Project Structure

- `cli.py` — Click CLI with all commands
- `advocate/agent/` — Autonomous agent core, MCP server, HTTP API, chat
- `advocate/knowledge/` — Doc ingestion, BM25 search, RAG vector index
- `advocate/content/` — Planner, writer, verifier, templates
- `advocate/growth/` — Experiments, SEO generation
- `advocate/feedback/` — Collector, exporter
- `advocate/social/` — Twitter agent, GitHub responder, Reddit scanner
- `advocate/site/` — Static site generator, templates, CSS
- `advocate/ledger.py` — Hash-chained audit trail
- `advocate/config.py` — Pydantic settings from .env

## DO NOT

- Auto-commit or push without explicit user permission
- Post tweets without showing the draft first
- Fabricate RevenueCat features — every claim must cite documentation
- Bypass safety gates (DRY_RUN, ALLOW_WRITES)
