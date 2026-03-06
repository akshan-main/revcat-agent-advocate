# Plan: RevenueCat Advocate OS -- Complete Build Specification

## Context

RevenueCat is hiring an autonomous AI agent as Developer & Growth Advocate (6-month, $10K/mo contract). The application must be submitted by the agent itself as a public URL. We're not writing a letter -- we're building a **live, auditable proof-of-work system** that generates content, runs experiments, files feedback, and publishes everything with a tamper-evident hash-chained ledger. The application URL points to a GitHub Pages site where reviewers can inspect every artifact, citation, and run log.

---

## Architecture (Complete File Tree)

```
revcat-advocate-os/
  pyproject.toml                    # Project config + all dependencies
  .env.example                      # All env vars with descriptions
  .gitignore                        # Ignore .docs_cache/, advocate.db, runs/, site_output/, .env
  README.md                         # Setup, commands, safety, ledger, architecture
  cli.py                            # Click CLI entrypoint (all commands)

  advocate/
    __init__.py                     # __version__ = "0.1.0"
    config.py                       # Pydantic settings from env
    db.py                           # SQLite 7-table schema + CRUD helpers
    models.py                       # All Pydantic models + enums
    ledger.py                       # Hash-chained tamper-evident run ledger

    knowledge/
      __init__.py
      ingest.py                     # LLM index download + .md mirror fetch + doc_sha256
      search.py                     # BM25-like search over cached docs

    revenuecat/
      __init__.py
      api.py                        # REST API v2 client (with safety gate)
      charts.py                     # Charts API client
      mcp.py                        # MCP client via official `mcp` Python SDK

    content/
      __init__.py
      planner.py                    # Topic selection + outlines via Claude API
      writer.py                     # Draft generation via Claude API
      verifier.py                   # Citation link check + snippet hash + doc_sha256 match
      templates/
        tutorial.md                 # Jinja2 markdown template
        case_study.md               # Jinja2 markdown template
        agent_playbook.md           # Jinja2 markdown template

    growth/
      __init__.py
      experiments.py                # Experiment registry + lifecycle
      seo.py                        # Programmatic SEO generator (10 pages)

    community/
      __init__.py
      tracker.py                    # Interaction logger (CRUD)
      responder.py                  # Draft response generator (safe mode ONLY)

    feedback/
      __init__.py
      collector.py                  # Structured feedback objects + auto-generation
      exporter.py                   # Markdown reports + optional GitHub Issues

    reporting/
      __init__.py
      weekly.py                     # Weekly report generator from DB

    site/
      __init__.py
      generator.py                  # Static site builder (Jinja2 HTML)
      templates/
        base.html                   # Shared layout: nav, footer, CSS link
        apply.html                  # Application letter page
        ledger.html                 # Run history + chain verification badge
        content.html                # Content index (posts + SEO pages)
        content_detail.html         # Single post with sources section
        experiments.html            # Experiments index with status cards
        feedback.html               # Feedback reports with severity badges
        runbook.html                # Operator runbook page
        weekly_report.html          # Weekly report page
      assets/
        style.css                   # Clean, professional, responsive CSS

  demo/
    __init__.py
    mock_api.py                     # Mock RC API + Charts + MCP responses
    fixtures/
      sample_index.txt              # Subset of real LLM index (20 entries)
      sample_doc_charts.md          # Cached charts doc page
      sample_doc_auth.md            # Cached auth doc page
      sample_doc_mcp.md             # Cached MCP doc page
      sample_doc_getting_started.md # Cached getting-started page
      sample_doc_offerings.md       # Cached offerings page
      sample_api_project.json       # Mock project response
      sample_api_apps.json          # Mock apps list response
      sample_api_products.json      # Mock products list response
      sample_api_charts.json        # Mock charts timeseries response
      sample_mcp_tools.json         # Mock MCP list_tools response (all 26 tools)

  site_output/                      # Generated static site (GitHub Pages root)
    index.html                      # Redirect to /apply
    apply/index.html
    ledger/index.html
    content/index.html
    content/<slug>/index.html       # Per-post pages
    experiments/index.html
    feedback/index.html
    runbook/index.html
    assets/style.css

  runs/                             # Ledger JSON files (one per run)

  tests/
    __init__.py
    conftest.py                     # Shared fixtures
    test_config.py
    test_db.py
    test_ledger.py
    test_ingest.py
    test_search.py
    test_api.py
    test_mcp.py
    test_content.py
    test_verifier.py
    test_experiments.py
    test_feedback.py
    test_site_generator.py
    test_cli.py
    test_demo_run.py
    fixtures/
      sample_index.txt              # Symlink or copy of demo/fixtures/sample_index.txt
      sample_doc.md
      sample_api_response.json
```

---

## Dependencies

### pyproject.toml

```toml
[project]
name = "revcat-advocate-os"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "click>=8.0",
    "rich>=13.0",
    "jinja2>=3.1",
    "anthropic>=0.40",
    "mcp>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "pytest-asyncio>=0.23",
    "responses>=0.25",
    "ruff>=0.4",
]

[project.scripts]
revcat-advocate = "cli:main"
```

---

## Configuration

### .env.example

```bash
# RevenueCat API (optional -- use DEMO_MODE=true without it)
REVENUECAT_API_KEY=sk_your_secret_key_here
REVENUECAT_PROJECT_ID=proj_your_project_id

# Anthropic API (required for content generation)
ANTHROPIC_API_KEY=sk-ant-your_key_here

# GitHub (optional -- for publish-site and feedback export)
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO=username/revcat-advocate-os

# Safety flags
DEMO_MODE=false          # true = use mock API responses, label outputs [DEMO]
DRY_RUN=true             # true = no external posts, no GitHub issues, drafts only
ALLOW_WRITES=false       # true = allow POST/PUT/DELETE to RC API (default: read-only)

# Ledger
LEDGER_HMAC_KEY=         # optional -- if set, signs each ledger entry with HMAC-SHA256

# Paths
DB_PATH=./advocate.db
DOCS_CACHE_DIR=./.docs_cache
SITE_OUTPUT_DIR=./site_output
RUNS_DIR=./runs
```

### advocate/config.py -- Full Spec

```python
from pydantic_settings import BaseSettings
from pydantic import field_validator

class Config(BaseSettings):
    # RevenueCat
    revenuecat_api_key: str | None = None
    revenuecat_project_id: str | None = None

    # Anthropic
    anthropic_api_key: str | None = None

    # GitHub
    github_token: str | None = None
    github_repo: str | None = None

    # Safety flags
    demo_mode: bool = False
    dry_run: bool = True
    allow_writes: bool = False

    # Ledger
    ledger_hmac_key: str | None = None

    # Paths
    db_path: str = "./advocate.db"
    docs_cache_dir: str = "./.docs_cache"
    site_output_dir: str = "./site_output"
    runs_dir: str = "./runs"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("revenuecat_api_key")
    @classmethod
    def validate_rc_key(cls, v):
        if v and not (v.startswith("sk_") or v.startswith("atk_")):
            raise ValueError("REVENUECAT_API_KEY must start with sk_ or atk_")
        return v

    @property
    def has_rc_credentials(self) -> bool:
        return self.revenuecat_api_key is not None

    @property
    def has_anthropic(self) -> bool:
        return self.anthropic_api_key is not None

    @property
    def has_github(self) -> bool:
        return self.github_token is not None and self.github_repo is not None

class SafetyError(Exception):
    """Raised when a safety gate blocks an operation."""
    pass
```

---

## Database Schema

### advocate/db.py -- Full SQL

```python
import sqlite3
import json
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS content_pieces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK(content_type IN ('tutorial', 'case_study', 'agent_playbook', 'seo_page')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'verified', 'published')),
    body_md TEXT,
    outline_json TEXT,
    sources_json TEXT,            -- JSON array of {url, doc_sha256, snippet_hashes}
    verification_json TEXT,       -- JSON object from verifier
    created_at TEXT NOT NULL,
    published_at TEXT,
    word_count INTEGER DEFAULT 0,
    citations_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS growth_experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    metric TEXT NOT NULL,
    channel TEXT NOT NULL,
    tactic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned', 'running', 'concluded')),
    inputs_json TEXT,
    outputs_json TEXT,            -- what was produced
    results_json TEXT,            -- measured outcomes
    duration_days INTEGER,
    created_at TEXT NOT NULL,
    concluded_at TEXT
);

CREATE TABLE IF NOT EXISTS community_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL CHECK(channel IN ('github', 'stackoverflow', 'discord', 'twitter', 'reddit', 'other')),
    thread_url TEXT,
    counterpart TEXT,             -- who we're responding to
    intent TEXT NOT NULL,         -- 'answer_question', 'share_resource', 'provide_feedback', 'engage'
    question TEXT,                -- the original question/post
    draft_response TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'queued', 'sent', 'skipped')),
    notes TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS product_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('critical', 'major', 'minor', 'suggestion')),
    area TEXT NOT NULL CHECK(area IN ('sdk', 'dashboard', 'api', 'docs', 'charts', 'paywalls', 'offerings', 'mcp', 'other')),
    repro_steps TEXT,
    expected TEXT,
    actual TEXT,
    evidence_links_json TEXT,     -- JSON array of URLs
    proposed_fix TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'exported', 'submitted')),
    github_issue_url TEXT,
    created_at TEXT NOT NULL,
    submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    sequence INTEGER NOT NULL,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    inputs_json TEXT,
    sources_json TEXT,
    tool_calls_json TEXT,
    outputs_json TEXT,
    verification_json TEXT,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL,
    signature TEXT,               -- HMAC signature if key configured
    success INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS seo_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    template_type TEXT NOT NULL CHECK(template_type IN ('comparison', 'how_to', 'glossary')),
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    body_md TEXT,
    sources_json TEXT,
    experiment_id INTEGER REFERENCES growth_experiments(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    path TEXT NOT NULL,
    doc_sha256 TEXT NOT NULL,
    content_length INTEGER,
    fetched_at TEXT NOT NULL,
    changed_from TEXT,            -- previous sha256 if updated
    UNIQUE(url, doc_sha256)
);

CREATE INDEX IF NOT EXISTS idx_content_status ON content_pieces(status);
CREATE INDEX IF NOT EXISTS idx_content_type ON content_pieces(content_type);
CREATE INDEX IF NOT EXISTS idx_run_log_command ON run_log(command);
CREATE INDEX IF NOT EXISTS idx_run_log_sequence ON run_log(sequence);
CREATE INDEX IF NOT EXISTS idx_doc_snapshots_url ON doc_snapshots(url);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON product_feedback(status);
CREATE INDEX IF NOT EXISTS idx_experiments_status ON growth_experiments(status);
"""

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

def insert_row(conn, table, data: dict) -> int:
    # JSON-encode any dict/list values
    # Return lastrowid

def query_rows(conn, table, where: dict | None = None, order_by: str = "id DESC", limit: int | None = None) -> list[dict]:
    # Generic query helper

def update_row(conn, table, row_id: int, data: dict):
    # Update specific row

def count_rows(conn, table, where: dict | None = None) -> int:
    # Count helper for reporting

def rows_since(conn, table, since: str, date_col: str = "created_at") -> list[dict]:
    # Get rows created/updated since a date (for weekly reports)
```

---

## Models

### advocate/models.py -- All Pydantic Models

```python
from pydantic import BaseModel
from enum import Enum
from datetime import datetime

# --- Enums ---
class ContentType(str, Enum):
    TUTORIAL = "tutorial"
    CASE_STUDY = "case_study"
    AGENT_PLAYBOOK = "agent_playbook"
    SEO_PAGE = "seo_page"

class ExperimentStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    CONCLUDED = "concluded"

class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"

class FeedbackArea(str, Enum):
    SDK = "sdk"
    DASHBOARD = "dashboard"
    API = "api"
    DOCS = "docs"
    CHARTS = "charts"
    PAYWALLS = "paywalls"
    OFFERINGS = "offerings"
    MCP = "mcp"
    OTHER = "other"

class InteractionChannel(str, Enum):
    GITHUB = "github"
    STACKOVERFLOW = "stackoverflow"
    DISCORD = "discord"
    TWITTER = "twitter"
    REDDIT = "reddit"
    OTHER = "other"

class InteractionIntent(str, Enum):
    ANSWER_QUESTION = "answer_question"
    SHARE_RESOURCE = "share_resource"
    PROVIDE_FEEDBACK = "provide_feedback"
    ENGAGE = "engage"

# --- Content ---
class Section(BaseModel):
    heading: str
    key_points: list[str]
    source_refs: list[str]          # doc URLs
    has_code_snippet: bool = False

class ContentOutline(BaseModel):
    title: str
    content_type: ContentType
    sections: list[Section]
    sources: list[str]              # all doc URLs used
    estimated_word_count: int

class SourceCitation(BaseModel):
    url: str
    doc_sha256: str
    sections_cited: int
    snippet_hashes: list[str]       # sha256 of each quoted snippet

class VerificationResult(BaseModel):
    citations_all_reachable: bool
    dead_links: list[str]
    snippet_syntax_valid: bool
    doc_sha256_matches: bool
    details: list[str]              # human-readable verification notes

class ContentPiece(BaseModel):
    slug: str
    title: str
    content_type: ContentType
    status: str = "draft"
    body_md: str = ""
    outline: ContentOutline | None = None
    sources: list[SourceCitation] = []
    verification: VerificationResult | None = None
    created_at: str = ""
    published_at: str | None = None
    word_count: int = 0
    citations_count: int = 0

# --- Growth ---
class ExperimentDefinition(BaseModel):
    name: str
    hypothesis: str
    metric: str
    channel: str
    tactic: str
    required_inputs: list[str]
    duration_days: int

class GrowthExperiment(BaseModel):
    name: str
    hypothesis: str
    metric: str
    channel: str
    tactic: str
    status: ExperimentStatus = ExperimentStatus.PLANNED
    inputs: dict = {}
    outputs: dict = {}
    results: dict = {}
    duration_days: int = 7
    created_at: str = ""
    concluded_at: str | None = None

# --- Community ---
class CommunityInteraction(BaseModel):
    channel: InteractionChannel
    thread_url: str = ""
    counterpart: str = ""
    intent: InteractionIntent
    question: str = ""
    draft_response: str = ""
    status: str = "draft"
    notes: str = ""
    created_at: str = ""
    sent_at: str | None = None

# --- Feedback ---
class ProductFeedback(BaseModel):
    title: str
    severity: Severity
    area: FeedbackArea
    repro_steps: str = ""
    expected: str = ""
    actual: str = ""
    evidence_links: list[str] = []
    proposed_fix: str = ""
    status: str = "new"
    github_issue_url: str | None = None
    created_at: str = ""
    submitted_at: str | None = None

# --- Search ---
class SearchResult(BaseModel):
    url: str
    path: str
    title: str
    score: float
    snippets: list[str]
    doc_sha256: str

# --- Ledger ---
class LedgerToolCall(BaseModel):
    tool: str
    params_summary: str = ""
    result_summary: str = ""

class LedgerSource(BaseModel):
    url: str
    doc_sha256: str
    sections_cited: int = 0
    snippet_hashes: list[str] = []

class LedgerOutputs(BaseModel):
    artifact_type: str = ""
    artifact_path: str = ""
    word_count: int = 0
    citations_count: int = 0
    code_snippets: int = 0
    additional: dict = {}

class RunEntry(BaseModel):
    run_id: str
    sequence: int
    prev_hash: str
    command: str
    started_at: str
    ended_at: str = ""
    inputs: dict = {}
    sources_used: list[LedgerSource] = []
    tool_calls: list[LedgerToolCall] = []
    outputs: LedgerOutputs = LedgerOutputs()
    verification: VerificationResult | None = None
    hash: str = ""
    signature: str | None = None
    success: bool = True

class ChainVerification(BaseModel):
    valid: bool
    total_entries: int
    breaks: list[int]               # sequence numbers where chain breaks
    hmac_verified: bool | None = None
```

---

## Tamper-Evident Hash-Chained Ledger

### advocate/ledger.py -- Full Spec

**Hash computation**:
1. Build `RunEntry` without `hash` and `signature` fields
2. Canonical JSON = `json.dumps(entry.model_dump(exclude={"hash", "signature"}), sort_keys=True, separators=(",", ":"))`
3. `hash = sha256(prev_hash_bytes + canonical_json_bytes).hexdigest()`
4. If `LEDGER_HMAC_KEY` set: `signature = hmac.new(key_bytes, hash_bytes, sha256).hexdigest()`

**Functions**:
```
start_run(db_conn, command: str, inputs: dict) -> RunContext
    - Creates RunContext with started_at, empty lists for tool_calls/sources
    - Looks up last sequence number + hash from run_log table
    - If no previous entry: prev_hash = "GENESIS", sequence = 1

class RunContext:
    run_id: str          # f"run_{timestamp}_{command}"
    sequence: int
    prev_hash: str
    command: str
    started_at: str
    inputs: dict
    tool_calls: list
    sources_used: list
    # Used as context manager: __enter__ / __exit__

log_tool_call(ctx: RunContext, tool: str, params_summary: str, result_summary: str)
    - Appends to ctx.tool_calls

log_source(ctx: RunContext, url: str, doc_sha256: str, snippet_hashes: list[str])
    - Appends to ctx.sources_used

finalize_run(ctx: RunContext, config: Config, db_conn, outputs: LedgerOutputs, verification: VerificationResult | None, success: bool = True) -> RunEntry
    - Sets ended_at
    - Builds RunEntry
    - Computes hash = sha256(prev_hash + canonical_json)
    - If config.ledger_hmac_key: computes signature
    - Inserts into run_log table
    - Writes runs/{run_id}.json file
    - Returns RunEntry

verify_chain(db_conn, config: Config | None = None) -> ChainVerification
    - SELECT * FROM run_log ORDER BY sequence ASC
    - Walk entries, recompute hash for each, compare
    - If config has HMAC key: also verify signatures
    - Return ChainVerification with valid, total_entries, breaks list
```

---

## Knowledge Engine

### advocate/knowledge/ingest.py -- Full Spec

**Constants**:
```
LLM_INDEX_URL = "https://www.revenuecat.com/docs/assets/files/llms-b3277dc1a771ac4b43dc7cfb88ebd955.txt"
DOCS_BASE_URL = "https://www.revenuecat.com/docs"
RATE_LIMIT_SECONDS = 0.3
MAX_RETRIES = 3
```

**Data classes**:
```
class DocEntry:
    path: str           # e.g. "dashboard-and-metrics/charts"
    title: str          # extracted from index line
    category: str       # top-level section
    url: str            # full URL

class IngestReport:
    total_entries: int
    fetched: int
    skipped: int        # already cached
    errored: int
    changed: int        # sha256 differed from cached
    errors: list[str]   # error details
```

**Functions**:
```
fetch_index(cache_dir: str) -> list[DocEntry]
    - GET LLM_INDEX_URL
    - Save raw text to cache_dir/index.txt
    - Parse: lines with URLs → extract path, title, category
    - Format: index is markdown with sections (## headings) and bullet items (- [title](url): description)
    - Return list of DocEntry

fetch_doc_page(entry: DocEntry, cache_dir: str, force: bool = False) -> tuple[str, str]
    - Target URL: f"{entry.url}.md"  (append .md for LLM-optimized markdown)
    - Cache path: cache_dir/pages/{sanitized_path}.md
    - If cached and not force: skip, return cached content + existing sha256
    - GET with requests.Session (retry adapter, 3 retries, exponential backoff)
    - Compute doc_sha256 = hashlib.sha256(content.encode()).hexdigest()
    - Save to cache path
    - Return (content, doc_sha256)

store_snapshot(db_conn, entry: DocEntry, doc_sha256: str, content_length: int, prev_sha256: str | None)
    - INSERT OR REPLACE into doc_snapshots
    - If prev_sha256 differs: set changed_from field

ingest_all(db_conn, config: Config, force: bool = False) -> IngestReport
    - fetch_index()
    - For each entry: fetch_doc_page(), store_snapshot()
    - Rate limit: time.sleep(RATE_LIMIT_SECONDS) between requests
    - Show rich.progress.Progress bar
    - Return IngestReport
    - Log to ledger
```

### advocate/knowledge/search.py -- Full Spec

**BM25 Parameters**:
```
K1 = 1.2    # term frequency saturation
B = 0.75    # document length normalization
```

**Data structures**:
```
class SearchIndex:
    doc_count: int
    avg_doc_length: float
    # inverted_index: dict[str, list[Posting]]
    # Posting: (doc_path, term_frequency, positions: list[int])
    # doc_lengths: dict[str, int]
    # doc_titles: dict[str, str]
    # doc_sha256s: dict[str, str]
```

**Functions**:
```
tokenize(text: str) -> list[str]
    - Lowercase, split on non-alphanumeric
    - Remove stopwords (minimal set: the, a, an, is, are, was, were, in, on, at, to, for, of, and, or)
    - Return tokens

build_index(cache_dir: str, db_conn) -> SearchIndex
    - Read all .md files from cache_dir/pages/
    - For each: tokenize, build postings
    - Compute avg_doc_length
    - Look up doc_sha256 from doc_snapshots table
    - Save index to cache_dir/_search_index.json
    - Return SearchIndex

bm25_score(term_freq, doc_length, avg_doc_length, doc_freq, total_docs) -> float
    - IDF = log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)
    - TF = (term_freq * (K1 + 1)) / (term_freq + K1 * (1 - B + B * doc_length / avg_doc_length))
    - Return IDF * TF

search(query: str, index: SearchIndex, top_k: int = 10) -> list[SearchResult]
    - Tokenize query
    - For each doc: sum BM25 scores across query terms
    - Sort by score descending
    - For each top-k result: extract snippets (sentences containing query terms, max 3 per result)
    - Return SearchResult list with url, path, title, score, snippets, doc_sha256

get_citation_url(path: str) -> str
    - Return f"https://www.revenuecat.com/docs/{path}"

format_citations(results: list[SearchResult]) -> str
    - Returns markdown block:
      ## Sources
      - [Title](url)
      - [Title](url)
```

---

## RevenueCat Connectivity

### advocate/revenuecat/api.py -- Full Spec

```
class RevenueCatAPIError(Exception):
    def __init__(self, status_code: int, message: str, body: dict | None):
        ...

class RevenueCatClient:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = "https://api.revenuecat.com/v2"
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {config.revenuecat_api_key}"
        self.session.headers["Content-Type"] = "application/json"
        # Add retry adapter: 3 retries, backoff_factor=1, retry on 429/500/502/503

    def _request(self, method: str, path: str, **kwargs) -> dict:
        - If method != "GET" and not config.allow_writes:
            raise SafetyError(f"Write operation blocked: {method} {path}. Set ALLOW_WRITES=true to allow.")
        - Make request
        - Handle 429: wait Retry-After header seconds, retry once
        - Handle 4xx/5xx: raise RevenueCatAPIError
        - Return response.json()

    def get_project(self) -> dict:
        return self._request("GET", f"/projects/{self.config.revenuecat_project_id}")

    def list_apps(self) -> dict:
        return self._request("GET", f"/projects/{self.config.revenuecat_project_id}/apps")

    def list_products(self, app_id: str) -> dict:
        return self._request("GET", f"/projects/{self.config.revenuecat_project_id}/apps/{app_id}/products")

    def list_offerings(self) -> dict:
        return self._request("GET", f"/projects/{self.config.revenuecat_project_id}/offerings")

    def list_entitlements(self) -> dict:
        return self._request("GET", f"/projects/{self.config.revenuecat_project_id}/entitlements")

    def get_customer(self, customer_id: str) -> dict:
        return self._request("GET", f"/projects/{self.config.revenuecat_project_id}/customers/{customer_id}")
```

### advocate/revenuecat/charts.py -- Full Spec

```
class ChartsMetric(str, Enum):
    MRR = "mrr"
    ARR = "arr"
    REVENUE = "revenue"
    ACTIVE_SUBSCRIPTIONS = "active_subscriptions"
    ACTIVE_TRIALS = "active_trials"
    CHURN = "churn"
    LTV = "ltv"
    REFUNDS = "refunds"
    NEW_CUSTOMERS = "new_customers"
    CONVERSIONS = "conversions"

class ChartData(BaseModel):
    metric: str
    start_date: str
    end_date: str
    resolution: str
    values: list[dict]   # [{date: str, value: float}, ...]
    filters: dict = {}

CHARTS_CAVEAT = (
    "Note: Charts data is based on current purchase receipt snapshots "
    "and reflects production data only (sandbox excluded). "
    "All times are UTC. Historical values may change if refunds occur. "
    "Data may differ from store reports if not all receipts pass through RevenueCat."
)

class ChartsClient:
    def __init__(self, config: Config):
        self.config = config
        # Uses same session setup as RevenueCatClient

    def query_chart(self, metric: ChartsMetric, start_date: str, end_date: str,
                    resolution: str = "day", filters: dict | None = None) -> ChartData:
        - GET /v2/projects/{project_id}/charts/{metric}
        - Params: start_date, end_date, resolution
        - Returns ChartData

    def summarize(self, data: ChartData) -> str:
        - Generates human-readable markdown summary
        - Always appends CHARTS_CAVEAT
        - Example: "MRR from 2026-02-01 to 2026-03-01: $12,345 → $14,567 (+18%)\n\n{CHARTS_CAVEAT}"
```

### advocate/revenuecat/mcp.py -- Full Spec

Uses official `mcp` Python SDK with Streamable HTTP transport.

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import asyncio

MCP_ENDPOINT = "https://mcp.revenuecat.ai/mcp"

# Read-only tools (safe without ALLOW_WRITES)
READ_ONLY_TOOLS = {
    "get-project-info", "list-apps", "list-products",
    "list-offerings", "list-entitlements", "get-customer",
    "query-charts", "list-subscribers", "get-subscriber",
    "list-packages",
}

class RevenueCatMCP:
    def __init__(self, config: Config):
        self.config = config
        self.endpoint = MCP_ENDPOINT
        self.session: ClientSession | None = None

    async def connect(self):
        """Initialize MCP session via Streamable HTTP"""
        headers = {"Authorization": f"Bearer {self.config.revenuecat_api_key}"}
        # Use mcp SDK's streamablehttp_client context manager
        # Store session for reuse

    async def list_tools(self) -> list[dict]:
        """Discover all RC MCP tools -- returns tool names + descriptions"""
        result = await self.session.list_tools()
        return [{"name": t.name, "description": t.description} for t in result.tools]

    async def call_tool(self, name: str, params: dict) -> dict:
        """Call a specific MCP tool with safety gate"""
        if name not in READ_ONLY_TOOLS and not self.config.allow_writes:
            raise SafetyError(f"MCP tool '{name}' requires ALLOW_WRITES=true")
        result = await self.session.call_tool(name, params)
        return result

    async def disconnect(self):
        """Close MCP session"""

# Sync wrapper for use in non-async CLI code
def run_mcp_sync(config: Config, tool_name: str, params: dict) -> dict:
    """Synchronous wrapper around async MCP calls"""
    async def _run():
        client = RevenueCatMCP(config)
        try:
            await client.connect()
            return await client.call_tool(tool_name, params)
        finally:
            await client.disconnect()
    return asyncio.run(_run())

def list_mcp_tools_sync(config: Config) -> list[dict]:
    """Synchronous wrapper to discover MCP tools"""
    async def _run():
        client = RevenueCatMCP(config)
        try:
            await client.connect()
            return await client.list_tools()
        finally:
            await client.disconnect()
    return asyncio.run(_run())
```

**Fallback pattern** (used throughout CLI commands):
```python
try:
    result = list_mcp_tools_sync(config)
    ledger.log_tool_call(ctx, "mcp.list_tools", "", f"{len(result)} tools discovered")
except Exception as e:
    # Fall back to REST
    result = rest_client.list_apps()
    ledger.log_tool_call(ctx, "rest.list_apps", "", f"MCP failed ({e}), fell back to REST")
```

---

## Content Engine

### advocate/content/planner.py -- Full Spec

```
SUGGESTED_TOPICS = [
    # These are generated dynamically from doc categories, but here are seed topics:
    "Getting Started with RevenueCat Charts API for Agent Dashboards",
    "Building Agent-Native Monetization with RevenueCat MCP Server",
    "RevenueCat Offerings and Paywalls: A Technical Deep Dive for Agents",
    "Implementing Subscription Analytics with the RevenueCat REST API v2",
    "How Agentic AI Apps Should Handle In-App Purchase Lifecycle Events",
]

def suggest_topics(search_index: SearchIndex, count: int = 5) -> list[str]:
    - Analyze doc categories for coverage gaps
    - Combine with SUGGESTED_TOPICS
    - Return top N topics

def create_outline(topic: str, content_type: ContentType, search_results: list[SearchResult],
                   config: Config) -> ContentOutline:
    - If config.has_anthropic:
        - System prompt: "You are a technical content planner for RevenueCat developer documentation.
          Create a structured outline for a {content_type} about '{topic}'.
          Use ONLY information from the provided documentation snippets.
          Each section must reference specific documentation sources."
        - User prompt: include search results with URLs and snippets
        - Parse Claude response into ContentOutline
    - Else (no Anthropic key):
        - Create a basic outline from search result titles and snippets
        - Less natural but functional
    - Return ContentOutline with sources populated
```

### advocate/content/writer.py -- Full Spec

**System prompt for Claude API**:
```
WRITER_SYSTEM_PROMPT = """You are a technical writer for RevenueCat, creating content for developers
building apps with in-app subscriptions. You are writing a {content_type}.

CRITICAL RULES:
1. Every factual claim about RevenueCat MUST include a citation in the format [Source](url).
2. Never fabricate features, API endpoints, pricing, or metrics that are not in the provided documentation.
3. Code examples must use real RevenueCat API patterns from the documentation.
4. If you are unsure about something, say "refer to the documentation" rather than guessing.
5. Include a ## Sources section at the end listing all cited documentation pages.

You will be provided with:
- A content outline with section headings and key points
- Relevant documentation snippets with their source URLs
- The content type (tutorial, case study, or agent playbook)

Write the complete article in Markdown with YAML front matter."""
```

```
def generate_draft(outline: ContentOutline, doc_snippets: dict[str, str],
                   config: Config, ledger_ctx: RunContext) -> str:
    - If config.has_anthropic:
        - Call anthropic.messages.create with:
            model = "claude-sonnet-4-6"
            system = WRITER_SYSTEM_PROMPT.format(content_type=outline.content_type)
            messages = [user message with outline + doc snippets]
            max_tokens = 4096
        - Log tool call to ledger
        - Return response text
    - Else:
        - Use Jinja2 template to assemble from outline + snippets
        - Less natural but still includes citations
        - Return rendered template

def save_draft(body_md: str, slug: str, output_dir: str) -> str:
    - Create directory: output_dir/content/{slug}/
    - Write body_md to output_dir/content/{slug}/index.md
    - Return path

def extract_code_snippets(body_md: str) -> list[tuple[str, str]]:
    - Parse markdown for ```python, ```javascript, ```swift etc. blocks
    - Return list of (language, code) tuples
    - These are saved alongside the post for testing

def save_code_snippets(snippets: list[tuple[str, str]], slug: str, output_dir: str) -> list[str]:
    - Save each snippet as output_dir/content/{slug}/snippet_{i}.{ext}
    - Return list of paths

def record_content(db_conn, piece: ContentPiece) -> int:
    - Insert into content_pieces table
    - Return row id
```

### advocate/content/verifier.py -- Full Spec

```
class VerificationReport:
    links_checked: int
    links_reachable: int
    dead_links: list[str]
    snippets_checked: int
    snippets_valid: int
    snippet_errors: list[str]
    doc_sha256_checks: int
    doc_sha256_matches: int
    doc_sha256_mismatches: list[str]
    overall_pass: bool

def verify_citations(body_md: str, timeout: int = 10) -> tuple[list[str], list[str]]:
    - Extract all [Source](url) and [text](url) links from markdown
    - For each URL: HEAD request (fallback GET if HEAD returns 405)
    - Return (reachable_urls, dead_urls)

def verify_snippet_hashes(body_md: str, cache_dir: str) -> tuple[list[str], list[str]]:
    - For each citation URL in the post:
        - Find the corresponding cached .md file
        - For each quoted passage (text between > blockquotes or inline quotes):
            - Compute snippet_sha256 = sha256(quoted_text.strip())
            - Check if quoted_text exists as substring in cached doc
        - Return (valid_hashes, invalid_hashes)

def verify_doc_sha256(sources: list[SourceCitation], db_conn) -> tuple[list[str], list[str]]:
    - For each source:
        - Look up doc_sha256 in doc_snapshots table for that URL
        - Compare with source.doc_sha256
    - Return (matches, mismatches)

def verify_code_snippets(snippet_paths: list[str]) -> tuple[list[str], list[str]]:
    - For each snippet file:
        - If .py: run py_compile.compile() to check syntax
        - If .js: basic regex check for syntax errors (or skip)
        - If .swift: skip (no local compiler expected)
    - Return (valid_paths, error_paths)

def full_verify(body_md: str, sources: list[SourceCitation],
                snippet_paths: list[str], cache_dir: str, db_conn) -> VerificationReport:
    - Run all verification checks
    - Return combined VerificationReport
    - overall_pass = no dead links AND no sha256 mismatches AND no snippet errors
```

---

## Content Templates

### advocate/content/templates/tutorial.md

```markdown
---
title: "{{ title }}"
date: "{{ date }}"
type: tutorial
tags: [{{ tags | join(', ') }}]
---

# {{ title }}

## Introduction

{{ intro }}

## Prerequisites

{{ prerequisites }}

{% for section in sections %}
## {{ section.heading }}

{{ section.body }}

{% if section.has_code_snippet %}
```{{ section.snippet_language }}
{{ section.snippet_code }}
```
{% endif %}

{% endfor %}

## Key Takeaways

{{ takeaways }}

## Next Steps

{{ next_steps }}

## Sources

{% for source in sources %}
- [{{ source.title }}]({{ source.url }})
{% endfor %}
```

### advocate/content/templates/case_study.md

```markdown
---
title: "{{ title }}"
date: "{{ date }}"
type: case_study
tags: [{{ tags | join(', ') }}]
---

# {{ title }}

## The Challenge

{{ challenge }}

## The Solution

{{ solution }}

## Implementation with RevenueCat

{% for section in sections %}
### {{ section.heading }}

{{ section.body }}

{% if section.has_code_snippet %}
```{{ section.snippet_language }}
{{ section.snippet_code }}
```
{% endif %}

{% endfor %}

## Results

{{ results }}

## Lessons Learned

{{ lessons }}

## Sources

{% for source in sources %}
- [{{ source.title }}]({{ source.url }})
{% endfor %}
```

### advocate/content/templates/agent_playbook.md

```markdown
---
title: "{{ title }}"
date: "{{ date }}"
type: agent_playbook
tags: [{{ tags | join(', ') }}]
---

# {{ title }}

## Goal

{{ goal }}

## Tools Required

{{ tools }}

## Agent Configuration

{{ configuration }}

## Workflow

{% for section in sections %}
### Step {{ loop.index }}: {{ section.heading }}

{{ section.body }}

{% if section.has_code_snippet %}
```{{ section.snippet_language }}
{{ section.snippet_code }}
```
{% endif %}

{% endfor %}

## Monitoring & Verification

{{ monitoring }}

## Sources

{% for source in sources %}
- [{{ source.title }}]({{ source.url }})
{% endfor %}
```

---

## Growth Engine

### advocate/growth/experiments.py -- Full Spec

```python
EXPERIMENT_REGISTRY = {
    "programmatic-seo": ExperimentDefinition(
        name="programmatic-seo",
        hypothesis="Generating 10 SEO-optimized pages targeting long-tail RevenueCat keywords will increase discoverability",
        metric="pages_generated",
        channel="organic_search",
        tactic="Generate comparison, how-to, and glossary pages from templates using ingested docs",
        required_inputs=["keywords_or_auto"],
        duration_days=30,
    ),
    "content-series": ExperimentDefinition(
        name="content-series",
        hypothesis="Publishing a 5-part tutorial series drives more engagement than standalone posts",
        metric="posts_published",
        channel="blog",
        tactic="Write a connected series of tutorials on a single RevenueCat feature area",
        required_inputs=["theme", "count"],
        duration_days=14,
    ),
    "community-blitz": ExperimentDefinition(
        name="community-blitz",
        hypothesis="Answering 20 questions in 48 hours with cited docs establishes authority",
        metric="interactions_completed",
        channel="github_stackoverflow",
        tactic="Find and draft responses to top unanswered RevenueCat questions",
        required_inputs=["target_count"],
        duration_days=2,
    ),
    "integration-showcase": ExperimentDefinition(
        name="integration-showcase",
        hypothesis="Integration guides for top platforms drive adoption among new developers",
        metric="guides_published",
        channel="blog",
        tactic="Write integration guides for Flutter, React Native, Unity, SwiftUI, Kotlin",
        required_inputs=["platforms"],
        duration_days=14,
    ),
}

def start_experiment(db_conn, name: str, inputs: dict) -> int:
    - Validate name exists in EXPERIMENT_REGISTRY
    - Validate required_inputs are provided
    - Insert into growth_experiments with status="running"
    - Return row id

def get_experiment(db_conn, experiment_id: int) -> GrowthExperiment:
    - Query by id, return model

def conclude_experiment(db_conn, experiment_id: int, results: dict):
    - Update status="concluded", results_json, concluded_at
```

### advocate/growth/seo.py -- Full Spec

```python
# Default keywords for programmatic SEO
DEFAULT_SEO_KEYWORDS = [
    "RevenueCat vs Adapty",
    "RevenueCat vs Qonversion",
    "RevenueCat vs Glassfy",
    "How to implement subscriptions with RevenueCat",
    "How to add paywalls with RevenueCat",
    "How to track MRR with RevenueCat Charts",
    "What is RevenueCat MCP server",
    "RevenueCat API v2 getting started",
    "RevenueCat subscription analytics for agents",
    "In-app purchase monetization for AI-built apps",
]

SEO_TEMPLATES = {
    "comparison": "## {keyword}\n\n### Overview\n{overview}\n\n### Feature Comparison\n{comparison}\n\n### Why RevenueCat\n{why_rc}\n\n### Sources\n{sources}",
    "how_to": "## {keyword}\n\n### What You'll Learn\n{intro}\n\n### Steps\n{steps}\n\n### Code Example\n{code}\n\n### Sources\n{sources}",
    "glossary": "## {keyword}\n\n### Definition\n{definition}\n\n### How It Works in RevenueCat\n{how_it_works}\n\n### Sources\n{sources}",
}

def determine_template_type(keyword: str) -> str:
    - If "vs" in keyword: return "comparison"
    - If keyword starts with "How to": return "how_to"
    - Else: return "glossary"

def generate_seo_page(keyword: str, search_results: list[SearchResult],
                      config: Config, ledger_ctx: RunContext) -> tuple[str, str]:
    - Determine template type
    - If config.has_anthropic:
        - Generate content via Claude API with doc context
        - Enforce citations
    - Else:
        - Fill template from search result snippets
    - slug = slugify(keyword)
    - Return (body_md, slug)

def bulk_generate(db_conn, config: Config, search_index: SearchIndex,
                  keywords: list[str] | None, experiment_id: int,
                  ledger_ctx: RunContext) -> list[str]:
    - If keywords is None: use DEFAULT_SEO_KEYWORDS
    - For each keyword:
        - Search docs for keyword
        - generate_seo_page()
        - Save to site_output/content/{slug}/index.md
        - Insert into seo_pages table (with experiment_id FK)
    - Return list of slugs
```

---

## Community & Feedback

### advocate/community/tracker.py

```
def log_interaction(db_conn, interaction: CommunityInteraction) -> int:
    - Insert into community_interactions
    - Return row id

def list_interactions(db_conn, channel: str | None = None, status: str | None = None,
                      since: str | None = None) -> list[CommunityInteraction]:
    - Query with optional filters

def update_interaction_status(db_conn, interaction_id: int, status: str, sent_at: str | None = None):
    - Update row
```

### advocate/community/responder.py

```
def draft_response(question: str, search_results: list[SearchResult],
                   config: Config, ledger_ctx: RunContext) -> str:
    - If config.has_anthropic:
        - System prompt: "You are a helpful RevenueCat developer advocate.
          Answer the question using ONLY the provided documentation.
          Include [Source](url) citations for every factual claim.
          Be concise and actionable."
        - Return response
    - Else:
        - Assemble response from search result snippets with citations

def queue_responses(db_conn, questions: list[dict], search_index: SearchIndex,
                    config: Config, ledger_ctx: RunContext) -> list[int]:
    - For each question:
        - Search docs for relevant context
        - draft_response()
        - log_interaction() with status="draft"
    - NEVER auto-post. status is always "draft".
    - Return list of interaction IDs
```

### advocate/feedback/collector.py

```
def create_feedback(title: str, severity: Severity, area: FeedbackArea,
                    repro_steps: str, expected: str, actual: str,
                    evidence_links: list[str], proposed_fix: str = "") -> ProductFeedback:
    - Validate via Pydantic
    - Return ProductFeedback model

def save_feedback(db_conn, feedback: ProductFeedback) -> int:
    - Insert into product_feedback
    - Return row id

def generate_feedback_from_docs(search_index: SearchIndex, config: Config,
                                 db_conn, ledger_ctx: RunContext,
                                 count: int = 3) -> list[ProductFeedback]:
    - If config.has_anthropic:
        - System prompt: "You are a QA engineer reviewing RevenueCat documentation.
          Analyze the provided documentation snippets and identify:
          1. Inconsistencies between docs pages
          2. Missing information that developers would need
          3. Unclear or confusing explanations
          4. API endpoints mentioned without examples
          For each issue, provide: title, severity, area, repro_steps (how a developer would encounter this),
          expected (what should be there), actual (what is there), and proposed_fix."
        - Send a batch of search results covering different doc areas
        - Parse response into ProductFeedback list
    - Else:
        - Generate generic feedback about common doc issues
    - Save each to DB
    - Return list of ProductFeedback
```

### advocate/feedback/exporter.py

```
def export_to_markdown(feedback: ProductFeedback) -> str:
    - Render structured markdown:
      # {title}
      **Severity**: {severity} | **Area**: {area}
      ## Reproduction Steps
      {repro_steps}
      ## Expected Behavior
      {expected}
      ## Actual Behavior
      {actual}
      ## Evidence
      {evidence_links as bullet list}
      ## Proposed Fix
      {proposed_fix}

def export_to_github_issue(feedback: ProductFeedback, config: Config) -> str | None:
    - If not config.has_github or config.dry_run:
        return None (log why)
    - POST to GitHub API: repos/{repo}/issues
    - Title: f"[{severity}] [{area}] {title}"
    - Body: export_to_markdown(feedback)
    - Labels: [severity, area, "advocate-os"]
    - Return issue URL

def export_batch(db_conn, config: Config, status: str = "new") -> list[str]:
    - Query all feedback with status
    - For each: export_to_markdown, optionally export_to_github_issue
    - Update status to "exported"
    - Return list of paths/URLs
```

---

## Reporting

### advocate/reporting/weekly.py -- Full Spec

```
def generate_weekly_report(db_conn, config: Config, charts_client=None,
                           week_start: str | None = None) -> str:
    - If week_start is None: use 7 days ago
    - Query each table for rows since week_start
    - Build markdown report:

    # Weekly Report -- {week_start} to {week_end}

    ## Summary
    | Metric | Count |
    |--------|-------|
    | Content published | {N} |
    | SEO pages generated | {N} |
    | Experiments active | {N} |
    | Community interactions | {N} |
    | Product feedback filed | {N} |
    | Ledger entries | {N} |
    | Chain status | Verified / Broken |

    ## Content Published
    {for each content_piece: title, type, slug, citations_count, word_count}

    ## Growth Experiments
    {for each experiment: name, hypothesis, status, key results}

    ## Community Interactions
    {count by channel, top 3 interactions by detail}

    ## Product Feedback
    {for each feedback: title, severity, area, status}

    ## Charts Snapshot (if available)
    {charts_client.summarize() for MRR + active subs}
    {CHARTS_CAVEAT}

    ## Ledger Statistics
    {total runs, success rate}
    {chain verification result}

    ## Next Week Plan
    {auto-suggest: topics to write, experiments to run}

def save_report(report: str, output_dir: str) -> str:
    - Save to output_dir/reports/week_{date}.md
    - Return path
```

---

## Static Site Generator

### advocate/site/generator.py -- Full Spec

```
def build_site(db_conn, config: Config):
    - Create output dirs: apply/, ledger/, content/, experiments/, feedback/, runbook/, assets/
    - Load all Jinja2 templates from advocate/site/templates/
    - Set up Jinja2 env with shared context: {site_title, build_date, chain_status}

    Step 1: Verify ledger chain
    - chain = verify_chain(db_conn, config)
    - Pass chain_status to all templates

    Step 2: Render /apply
    - Query: get application letter content (from content_pieces where slug="application-letter")
    - If not found: generate a placeholder
    - Render apply.html → site_output/apply/index.html

    Step 3: Render /ledger
    - Query: SELECT * FROM run_log ORDER BY sequence DESC
    - Also read runs/*.json for full detail
    - Render ledger.html → site_output/ledger/index.html
    - Include chain verification badge (green check or red X)

    Step 4: Render /content
    - Query: all content_pieces + seo_pages
    - Render content.html (index) → site_output/content/index.html
    - For each piece: render content_detail.html → site_output/content/{slug}/index.html
    - Content detail includes: full markdown body rendered to HTML, sources section, verification badge

    Step 5: Render /experiments
    - Query: all growth_experiments
    - Render experiments.html → site_output/experiments/index.html

    Step 6: Render /feedback
    - Query: all product_feedback
    - Render feedback.html → site_output/feedback/index.html

    Step 7: Render /runbook
    - Render runbook.html (static content) → site_output/runbook/index.html

    Step 8: Render index
    - Write site_output/index.html with meta redirect to /apply

    Step 9: Copy assets
    - Copy style.css → site_output/assets/style.css

def render_markdown_to_html(md_text: str) -> str:
    - Simple markdown-to-HTML conversion
    - Use a minimal regex-based converter (or add markdown as dependency)
    - Handle: headers, paragraphs, code blocks, links, lists, bold/italic, blockquotes
```

### Site Template Details

**base.html**:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ page_title }} -- RevenueCat Advocate OS</title>
    <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
    <nav>
        <div class="nav-brand">Advocate OS</div>
        <div class="nav-links">
            <a href="/apply">Apply</a>
            <a href="/content">Content</a>
            <a href="/experiments">Experiments</a>
            <a href="/feedback">Feedback</a>
            <a href="/ledger">Ledger</a>
            <a href="/runbook">Runbook</a>
        </div>
    </nav>
    <main>{% block content %}{% endblock %}</main>
    <footer>
        <p>Built by Advocate OS -- a tamper-evident proof-of-work agent system</p>
        <p>Chain status: <span class="{{ 'verified' if chain_status.valid else 'broken' }}">
            {{ 'Verified' if chain_status.valid else 'BROKEN' }} ({{ chain_status.total_entries }} entries)
        </span></p>
    </footer>
</body>
</html>
```

**ledger.html** key elements:
- Chain verification badge at top (green/red)
- Table of all runs: run_id, command, started_at, success, hash (truncated)
- Each row expandable (details/summary) to show full JSON
- Hash chain visualization: each entry shows prev_hash → hash arrow

**style.css** requirements:
- Clean sans-serif font (system fonts)
- Max-width 900px centered container
- Responsive down to mobile
- Color scheme: white bg, dark text, green for verified/success, red for broken/error
- Code blocks: monospace with light gray background
- Navigation: horizontal top bar
- Cards for experiments/feedback with border + subtle shadow
- No external CSS frameworks (pure CSS)

---

## CLI Commands

### cli.py -- Full Spec

```python
import click
from rich.console import Console
from rich.progress import Progress

@click.group()
@click.pass_context
def main(ctx):
    """RevenueCat Advocate OS -- Tamper-Evident Proof-of-Work Agent System"""
    ctx.ensure_object(dict)
    config = Config()
    ctx.obj["config"] = config
    ctx.obj["db"] = init_db(config.db_path)
    ctx.obj["console"] = Console()

# --- Commands ---

@main.command("ingest-docs")
@click.option("--force", is_flag=True, help="Re-fetch all pages even if cached")
@click.pass_context
def ingest_docs(ctx, force):
    """Download RevenueCat LLM docs index and fetch .md mirror pages."""
    # 1. start_run("ingest-docs", {"force": force})
    # 2. ingest_all()
    # 3. build_index()
    # 4. finalize_run with stats
    # 5. Print summary table

@main.command("write-content")
@click.option("--topic", required=True, help="Topic for the content piece")
@click.option("--type", "content_type", type=click.Choice(["tutorial", "case_study", "agent_playbook"]), default="tutorial")
@click.option("--count", default=1, help="Number of pieces to generate")
@click.pass_context
def write_content(ctx, topic, content_type, count):
    """Generate content with citations and verification."""
    # For each piece:
    # 1. start_run("write-content", {"topic": topic, "type": content_type})
    # 2. Search docs for topic
    # 3. create_outline()
    # 4. generate_draft()
    # 5. extract_code_snippets() + save_code_snippets()
    # 6. full_verify()
    # 7. save_draft()
    # 8. record_content() in DB
    # 9. finalize_run with outputs + verification
    # 10. Print summary: title, word count, citations, verification status

@main.command("run-experiment")
@click.option("--name", required=True, type=click.Choice(list(EXPERIMENT_REGISTRY.keys())))
@click.option("--inputs", default="{}", help="JSON string of experiment inputs")
@click.pass_context
def run_experiment(ctx, name, inputs):
    """Start a growth experiment."""
    # 1. start_run("run-experiment", {"name": name})
    # 2. start_experiment() in DB
    # 3. If "programmatic-seo": call bulk_generate()
    # 4. conclude_experiment() with results
    # 5. finalize_run
    # 6. Print experiment card

@main.command("generate-feedback")
@click.option("--count", default=3, help="Number of feedback items to generate")
@click.pass_context
def generate_feedback(ctx, count):
    """Generate structured product feedback from doc analysis."""
    # 1. start_run("generate-feedback", {"count": count})
    # 2. generate_feedback_from_docs()
    # 3. For each: save_feedback(), optionally export
    # 4. finalize_run
    # 5. Print feedback table

@main.command("queue-replies")
@click.option("--source", required=True, type=click.Choice(["github", "stackoverflow", "discord", "twitter", "reddit"]))
@click.option("--questions", type=click.Path(exists=True), help="JSON file with questions to respond to")
@click.pass_context
def queue_replies(ctx, source, questions):
    """Draft community responses (safe mode -- never auto-posts)."""
    # 1. Load questions from file (or interactive prompt)
    # 2. start_run("queue-replies", {"source": source, "count": len(questions)})
    # 3. queue_responses()
    # 4. finalize_run
    # 5. Print: "{N} responses drafted. Review in DB or /community."

@main.command("weekly-report")
@click.option("--with-charts", is_flag=True, help="Include Charts API metrics snapshot")
@click.pass_context
def weekly_report(ctx, with_charts):
    """Generate weekly activity report."""
    # 1. start_run("weekly-report", {"with_charts": with_charts})
    # 2. If with_charts and config.has_rc_credentials: create ChartsClient
    # 3. generate_weekly_report()
    # 4. save_report()
    # 5. finalize_run
    # 6. Print report to console

@main.command("build-site")
@click.pass_context
def build_site(ctx):
    """Build the static GitHub Pages site from DB and artifacts."""
    # 1. start_run("build-site", {})
    # 2. build_site()
    # 3. finalize_run with page counts
    # 4. Print: "Site built at {output_dir}. {N} pages generated."

@main.command("publish-site")
@click.pass_context
def publish_site(ctx):
    """Commit and push site_output/ to GitHub (if repo configured)."""
    # 1. Check config.has_github
    # 2. start_run("publish-site", {"repo": config.github_repo})
    # 3. git add site_output/
    # 4. git commit -m "Update Advocate OS site -- {date}"
    # 5. git push
    # 6. finalize_run
    # 7. Print: "Published to {repo}. Pages URL: ..."

@main.command("verify-ledger")
@click.pass_context
def verify_ledger(ctx):
    """Verify the hash chain integrity of the run ledger."""
    # 1. verify_chain()
    # 2. Print: "Chain verified: {N} entries, {breaks} breaks"
    # 3. If HMAC key: also verify signatures
    # 4. Print detailed results

@main.command("generate-application")
@click.pass_context
def generate_application(ctx):
    """Generate the /apply application letter."""
    # 1. start_run("generate-application", {})
    # 2. Search docs for key topics: MCP, Charts API, LLM index, .md mirrors
    # 3. Generate application letter via Claude API (see Application Letter section)
    # 4. Save as content_piece with slug="application-letter"
    # 5. finalize_run
    # 6. Print: "Application letter generated. Run build-site to publish."

@main.command("demo-run")
@click.pass_context
def demo_run(ctx):
    """Run full pipeline end-to-end (the mind-blow button)."""
    console = ctx.obj["console"]
    console.print("[bold]Advocate OS -- Full Demo Run[/bold]")
    console.print("=" * 50)

    # Step 1: Ingest docs
    console.print("\n[bold cyan]Step 1/8:[/bold cyan] Ingesting RevenueCat docs...")
    ctx.invoke(ingest_docs, force=False)

    # Step 2: Generate application letter
    console.print("\n[bold cyan]Step 2/8:[/bold cyan] Generating application letter...")
    ctx.invoke(generate_application)

    # Step 3: Write 2 content pieces
    console.print("\n[bold cyan]Step 3/8:[/bold cyan] Writing content piece 1...")
    ctx.invoke(write_content, topic="Using RevenueCat Charts API for Agent Dashboards", content_type="tutorial", count=1)
    console.print("\n[bold cyan]Step 4/8:[/bold cyan] Writing content piece 2...")
    ctx.invoke(write_content, topic="Building Agent-Native Monetization with RevenueCat MCP Server", content_type="agent_playbook", count=1)

    # Step 4: Run SEO experiment
    console.print("\n[bold cyan]Step 5/8:[/bold cyan] Running programmatic SEO experiment...")
    ctx.invoke(run_experiment, name="programmatic-seo", inputs="{}")

    # Step 5: Generate feedback
    console.print("\n[bold cyan]Step 6/8:[/bold cyan] Generating product feedback...")
    ctx.invoke(generate_feedback, count=3)

    # Step 6: Weekly report
    console.print("\n[bold cyan]Step 7/8:[/bold cyan] Generating weekly report...")
    ctx.invoke(weekly_report, with_charts=False)

    # Step 7: Build site
    console.print("\n[bold cyan]Step 8/8:[/bold cyan] Building static site...")
    ctx.invoke(build_site)

    # Step 8: Verify ledger
    console.print("\n[bold green]Verifying ledger chain...[/bold green]")
    ctx.invoke(verify_ledger)

    console.print("\n[bold green]Demo run complete![/bold green]")
    console.print(f"Site ready at: {ctx.obj['config'].site_output_dir}/")
    console.print("Preview: python -m http.server -d site_output 8000")
```

---

## Application Letter Content

### Generated for `/apply` page (via `generate-application` command)

The Claude API system prompt for generating the application letter:

```
APPLY_SYSTEM_PROMPT = """You are writing a public application letter for the RevenueCat Agentic AI
Developer & Growth Advocate role. This letter will be published at a URL and reviewed by RevenueCat's
hiring council.

CRITICAL: This is not a generic cover letter. This is a proof-of-work demonstration. The letter must:
1. Make a compelling argument about the future of agentic AI in app development
2. Show deep understanding of RevenueCat's ecosystem (cite specific docs)
3. Link to the live evidence: /ledger, /content, /experiments, /feedback
4. Close with "you're not hiring a promise, you're hiring a system that's already running"

Structure:
1. The Next 12 Months -- how agentic AI changes app development and growth
2. RevenueCat's Strategic Position -- MCP server, Charts API, LLM docs index with .md mirrors
3. Why This Agent -- link to all evidence sections
4. Operating Model -- weekly cadence, safety gates, audit trail
5. The Close -- receipts, not promises

IMPORTANT CREDIBILITY SIGNALS:
- Cite the LLM docs index and specifically mention the .md mirror trick
- Reference the MCP server's 26 tools and the Streamable HTTP transport
- Mention Charts API's Feb 2026 release and its receipt-snapshot basis
- Quote the exact claude mcp add command from RevenueCat docs
"""
```

---

## Demo Mode

### demo/mock_api.py -- Full Spec

```python
# When DEMO_MODE=true, all API calls route through these mocks

DEMO_BADGE = "[DEMO MODE -- Mock data, not real RevenueCat metrics]"

class MockRevenueCatClient:
    """Returns realistic-looking mock responses, all labeled [DEMO]."""

    def get_project(self) -> dict:
        return {"id": "proj_demo", "name": "Demo Project " + DEMO_BADGE, ...}

    def list_apps(self) -> dict:
        return {"items": [{"id": "app_demo_ios", "name": "Demo iOS App", ...}]}

    def list_products(self, app_id) -> dict:
        return {"items": [{"id": "prod_monthly", "name": "Monthly Premium " + DEMO_BADGE, ...}]}

    def list_offerings(self) -> dict:
        return {"items": [{"id": "offering_default", ...}]}

class MockChartsClient:
    """Returns demo timeseries data."""

    def query_chart(self, metric, start_date, end_date, **kwargs) -> ChartData:
        # Generate synthetic timeseries
        # All values clearly labeled as demo data

    def summarize(self, data) -> str:
        return f"{DEMO_BADGE}\nMRR: $0 (demo)\n..."

class MockMCPClient:
    """Returns mock MCP tool list."""

    def list_tools(self) -> list[dict]:
        # Load from demo/fixtures/sample_mcp_tools.json
        # This should list all 26 real tool names (from RC docs) with descriptions

    def call_tool(self, name, params) -> dict:
        return {"result": f"Mock result for {name}", "demo": True}
```

### demo/fixtures/ contents

**sample_index.txt**: First 20 entries from the real LLM index (enough for testing)
**sample_doc_*.md**: 5 real doc pages cached locally (charts, auth, MCP, getting-started, offerings)
**sample_api_*.json**: Realistic mock API responses matching RC API v2 schema
**sample_mcp_tools.json**: All 26 MCP tool names + descriptions (from RC MCP docs)

---

## Tests -- Full Spec

### tests/conftest.py

```python
import pytest
import sqlite3
import tempfile
import os

@pytest.fixture
def db_conn():
    """In-memory SQLite with schema initialized."""
    conn = init_db(":memory:")
    yield conn
    conn.close()

@pytest.fixture
def mock_config(tmp_path):
    """Config with test values, demo mode on."""
    return Config(
        demo_mode=True,
        dry_run=True,
        allow_writes=False,
        db_path=str(tmp_path / "test.db"),
        docs_cache_dir=str(tmp_path / "docs"),
        site_output_dir=str(tmp_path / "site"),
        runs_dir=str(tmp_path / "runs"),
    )

@pytest.fixture
def sample_docs_cache(tmp_path):
    """Temp dir with sample cached doc pages."""
    cache = tmp_path / "docs" / "pages"
    cache.mkdir(parents=True)
    (cache / "charts-overview.md").write_text("# Charts\nRevenueCat Charts show your metrics...")
    (cache / "authentication.md").write_text("# Authentication\nUse Bearer token...")
    return str(tmp_path / "docs")

@pytest.fixture
def sample_index_text():
    """Subset of real LLM index for testing."""
    return open("tests/fixtures/sample_index.txt").read()
```

### Test file specs

**test_config.py**:
- Test env var loading
- Test RC key validation (sk_ prefix)
- Test default values (dry_run=True, allow_writes=False)

**test_db.py**:
- Test schema creation
- Test insert_row + query_rows for each table
- Test update_row
- Test rows_since date filtering
- Test count_rows

**test_ledger.py** (CRITICAL):
- Test: create 3 runs, verify chain passes
- Test: tamper with run #2 JSON, verify chain reports break at #2
- Test: HMAC signature generation + validation
- Test: HMAC with wrong key fails verification
- Test: genesis entry has prev_hash="GENESIS"
- Test: sequence numbers are monotonically increasing
- Test: concurrent writes don't break chain (sequential in practice)

**test_ingest.py**:
- Test: parse_index extracts correct number of entries from sample_index.txt
- Test: each DocEntry has path, title, category
- Test: fetch_doc_page appends .md to URL (mock HTTP)
- Test: doc_sha256 is computed correctly
- Test: re-ingest with same content sets changed_from=None
- Test: re-ingest with changed content sets changed_from to old hash

**test_search.py**:
- Test: build_index over sample docs produces non-empty index
- Test: search("charts") returns charts doc as top result
- Test: search returns doc_sha256 with each result
- Test: BM25 scoring ranks exact matches higher

**test_api.py**:
- Test: safety gate blocks POST when allow_writes=False
- Test: safety gate allows GET always
- Test: safety gate allows POST when allow_writes=True
- Test: 429 retry behavior (mock 429 then 200)

**test_mcp.py**:
- Test: list_tools returns tool list (mocked)
- Test: call_tool with read-only tool works
- Test: call_tool with write tool blocked when allow_writes=False
- Test: fallback to REST when MCP connection fails

**test_content.py**:
- Test: create_outline returns ContentOutline with sections
- Test: generate_draft includes citation [Source](url) links
- Test: generated content has ## Sources section
- Test: extract_code_snippets finds code blocks

**test_verifier.py** (CRITICAL):
- Test: verify_citations finds dead links (mock 404 response)
- Test: verify_citations passes for valid links (mock 200)
- Test: verify_snippet_hashes matches against cached doc
- Test: verify_doc_sha256 detects mismatch
- Test: full_verify combines all checks

**test_experiments.py**:
- Test: start_experiment validates name against registry
- Test: start_experiment rejects unknown experiment name
- Test: conclude_experiment updates status and results
- Test: experiment lifecycle: planned → running → concluded

**test_feedback.py**:
- Test: create_feedback validates severity enum
- Test: create_feedback validates area enum
- Test: export_to_markdown produces correct structure
- Test: export_to_github_issue blocked in dry_run mode

**test_site_generator.py**:
- Test: build_site creates all expected directories
- Test: build_site creates index.html with redirect
- Test: apply page includes chain status badge
- Test: ledger page shows all run entries
- Test: content pages render markdown to HTML

**test_cli.py**:
- Test: CLI --help works
- Test: Each command accepts expected options
- Test: demo-run completes without error (with mocked services)

**test_demo_run.py** (INTEGRATION):
- Test: demo-run in demo mode produces:
  - site_output/apply/index.html (exists, non-empty)
  - site_output/ledger/index.html (exists, shows entries)
  - site_output/content/index.html (exists, lists 2+ posts)
  - site_output/experiments/index.html (exists, shows 1 experiment)
  - site_output/feedback/index.html (exists, shows 3 feedback items)
  - runs/ directory has 7+ JSON files
  - verify_chain returns valid=True

---

## Operator Runbook Page Content

### `/runbook` page contains:

```markdown
# Operator Runbook

## Quick Start (Demo Mode)
pip install -e .
export DEMO_MODE=true
export ANTHROPIC_API_KEY=sk-ant-...
revcat-advocate demo-run

## Quick Start (Real Mode)
pip install -e .
export REVENUECAT_API_KEY=sk_your_key
export ANTHROPIC_API_KEY=sk-ant-...
export DEMO_MODE=false
revcat-advocate ingest-docs
revcat-advocate write-content --topic "Your Topic" --type tutorial
revcat-advocate build-site

## Safety Gates
| Flag | Default | Effect |
|------|---------|--------|
| DRY_RUN | true | No external posts, no GitHub issues, drafts only |
| ALLOW_WRITES | false | Blocks POST/PUT/DELETE to RevenueCat API |
| DEMO_MODE | false | Uses mock API responses, labels all output [DEMO] |

## Where the Receipts Are
- /ledger -- Every action logged with hash chain. Click any entry to see full JSON.
- /content -- Every post has a Sources section with cited doc URLs.
- /experiments -- Every experiment has hypothesis, metric, and results.
- /feedback -- Every feedback item has repro steps and evidence links.

## Reproduce a Post
revcat-advocate write-content --topic "Charts API for Agents" --type tutorial
# Output: site_output/content/charts-api-for-agents/index.md
# Includes: outline, citations, code snippets, verification results

## Reproduce an Experiment
revcat-advocate run-experiment --name programmatic-seo
# Output: 10 SEO pages in site_output/content/
# DB record in growth_experiments table

## Verify the Ledger
revcat-advocate verify-ledger
# Expected: "Chain verified: N entries, 0 breaks"

## Architecture
Docs (LLM Index + .md mirrors)
    → Knowledge Engine (BM25 search)
        → Content Engine (Claude API + verification)
        → Growth Engine (experiments + SEO)
        → Feedback Engine (doc analysis)
    → Ledger (hash chain)
        → Static Site (GitHub Pages)

## MCP Setup (for Claude Code users)
claude mcp add revenuecat -t http -- https://mcp.revenuecat.ai/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"
```

---

## Post-Apply Strategy

### Keep shipping (built into the system)

After submitting `/apply`, keep the agent running:
- `write-content` 1-2x/week → new posts extend the ledger chain
- `build-site` + `publish-site` → live site shows growth, not a static snapshot
- Reviewers who check back see activity, not a one-shot demo

### Take-home readiness (48-hour turnaround)

When the take-home arrives:
1. `write-content --topic "<their prompt>" --type tutorial` -- reference-grade tutorial
2. `run-experiment --name <relevant>` -- growth experiment with artifacts
3. `generate-feedback --count 3` -- structured product feedback
4. `weekly-report` -- single clean deliverable
5. `build-site` + `publish-site` -- updated site with new work

Deliverable format: one report linking to URLs + why it matters + how validated + what's next.

### Panel interview demo flows (6 key demos)

1. **Docs ingestion**: `ingest-docs` → show doc_sha256 → search a term → show citation chain
2. **Content generation**: `write-content` → show outline → draft → verification pass
3. **Experiment execution**: `run-experiment` → hypothesis → artifacts → DB record → ledger
4. **Feedback generation**: `generate-feedback` → structured output with repro steps + evidence
5. **Safety gates**: `ALLOW_WRITES=false` blocks a POST → `DRY_RUN=true` keeps drafts as drafts
6. **Audit trail**: `verify-ledger` → green badge → explain hash chain

### Founder interview (operator)

The `/runbook` page is the operator's reference:
- Clear operating model: weekly cadence with measurable outputs
- Risk management: safety gates + dry-run defaults
- The argument: "Here's N content pieces, M experiments, K feedback items -- all with receipts"

---

## README.md Structure

```markdown
# RevenueCat Advocate OS

Tamper-evident proof-of-work agent system for the RevenueCat Agentic AI Developer & Growth Advocate role.

## What Is This?

An autonomous agent that ingests RevenueCat documentation, generates cited technical content,
runs growth experiments, files structured product feedback, and publishes everything to a
static site with a hash-chained audit trail. Every output is verifiable. Every claim has receipts.

## Quick Start

### Demo Mode (no RevenueCat credentials needed)
{exact commands}

### Real Mode
{exact commands}

## Commands
{table of all commands with descriptions}

## Safety Gates
{table: DRY_RUN, ALLOW_WRITES, DEMO_MODE with defaults and effects}

## Tamper-Evident Ledger
Every command creates a hash-chained log entry:
- `hash = sha256(prev_hash + canonical_json)`
- Optional HMAC signature via `LEDGER_HMAC_KEY`
- Verify: `revcat-advocate verify-ledger`
- Browse: /ledger on the published site

## MCP Integration
Uses the official `mcp` Python SDK with Streamable HTTP transport:
Endpoint: https://mcp.revenuecat.ai/mcp
Auth: Bearer token (same as API v2)

For Claude Code users:
claude mcp add revenuecat -t http -- https://mcp.revenuecat.ai/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"

## Architecture
{ASCII diagram}

## Development
pip install -e ".[dev]"
pytest tests/ -v
```

---

## .gitignore

```
.env
advocate.db
.docs_cache/
site_output/
runs/
__pycache__/
*.pyc
.pytest_cache/
dist/
*.egg-info/
```

---

## Verification (End-to-End Smoke Test)

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Configure (demo mode)
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY, set DEMO_MODE=true

# 3. Full pipeline
revcat-advocate demo-run

# 4. Verify outputs
ls site_output/apply/          # Application letter
ls site_output/ledger/         # Ledger page
ls site_output/content/        # 2 posts + 10 SEO pages
ls site_output/experiments/    # 1 experiment
ls site_output/feedback/       # 3 feedback reports
ls site_output/runbook/        # Operator runbook
ls runs/                       # 8+ JSON ledger files

# 5. Verify chain
revcat-advocate verify-ledger
# Expected: "Chain verified: N entries, 0 breaks"

# 6. Run tests
pytest tests/ -v
# All must pass

# 7. Preview locally
python -m http.server -d site_output 8000
# Browse http://localhost:8000
# Check: all pages render, nav works, ledger shows green badge

# 8. Publish (when ready)
revcat-advocate publish-site
# Submit the /apply URL to RevenueCat careers page
```

---

## Site Pages Summary

| Route | Purpose | Content Source |
|-------|---------|---------------|
| `/` | Landing → redirect to `/apply` | Static HTML meta redirect |
| `/apply` | Application letter | `content_pieces` where slug="application-letter" |
| `/ledger` | Hash-chained run history | `run_log` table + `runs/*.json` |
| `/content` | Content index | `content_pieces` + `seo_pages` tables |
| `/content/<slug>` | Individual posts | Generated markdown → HTML |
| `/experiments` | Growth experiments | `growth_experiments` table |
| `/feedback` | Product feedback | `product_feedback` table |
| `/runbook` | Operator runbook | Static template |
