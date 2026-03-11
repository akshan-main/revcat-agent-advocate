import json
from datetime import datetime, timezone

import libsql_experimental as libsql

SCHEMA = """
CREATE TABLE IF NOT EXISTS content_pieces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK(content_type IN ('tutorial', 'case_study', 'agent_playbook', 'seo_page')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'verified', 'published')),
    body_md TEXT,
    outline_json TEXT,
    sources_json TEXT,
    verification_json TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    word_count INTEGER DEFAULT 0,
    citations_count INTEGER DEFAULT 0,
    devto_article_id INTEGER,
    devto_url TEXT,
    devto_views INTEGER DEFAULT 0,
    devto_reactions INTEGER DEFAULT 0,
    devto_comments INTEGER DEFAULT 0,
    devto_synced_at TEXT
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
    outputs_json TEXT,
    results_json TEXT,
    duration_days INTEGER,
    created_at TEXT NOT NULL,
    concluded_at TEXT
);

CREATE TABLE IF NOT EXISTS community_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL CHECK(channel IN ('github', 'stackoverflow', 'discord', 'twitter', 'reddit', 'other')),
    thread_url TEXT,
    counterpart TEXT,
    intent TEXT NOT NULL,
    question TEXT,
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
    evidence_links_json TEXT,
    proposed_fix TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'exported', 'submitted')),
    github_issue_url TEXT,
    created_at TEXT NOT NULL,
    submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    sequence INTEGER NOT NULL UNIQUE,
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
    signature TEXT,
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
    changed_from TEXT,
    UNIQUE(url, doc_sha256)
);

CREATE TABLE IF NOT EXISTS agent_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT,
    lesson_type TEXT NOT NULL CHECK(lesson_type IN ('content_perf', 'topic_signal', 'channel_insight', 'strategy', 'failure')),
    key TEXT NOT NULL,
    insight TEXT NOT NULL,
    evidence TEXT,
    confidence REAL DEFAULT 0.5,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_type ON agent_memory(lesson_type);
CREATE INDEX IF NOT EXISTS idx_content_status ON content_pieces(status);
CREATE INDEX IF NOT EXISTS idx_content_type ON content_pieces(content_type);
CREATE INDEX IF NOT EXISTS idx_run_log_command ON run_log(command);
CREATE INDEX IF NOT EXISTS idx_run_log_sequence ON run_log(sequence);
CREATE INDEX IF NOT EXISTS idx_doc_snapshots_url ON doc_snapshots(url);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON product_feedback(status);
CREATE INDEX IF NOT EXISTS idx_experiments_status ON growth_experiments(status);
"""


class _DictCursor:
    """Wraps a cursor to return dicts instead of tuples (for libsql compatibility)."""

    def __init__(self, cursor):
        self._cursor = cursor

    def _to_dict(self, row):
        if row is None:
            return None
        cols = [d[0] for d in self._cursor.description]
        return dict(zip(cols, row))

    def fetchone(self):
        row = self._cursor.fetchone()
        return self._to_dict(row)

    def fetchall(self):
        return [self._to_dict(row) for row in self._cursor.fetchall()]

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def description(self):
        return self._cursor.description


class DBConnection:
    """Unified database connection wrapping libsql (Turso cloud or local)."""

    def __init__(self, conn, is_turso: bool = False):
        self._conn = conn
        self._is_turso = is_turso

    def execute(self, sql, params=None):
        if params:
            cursor = self._conn.execute(sql, tuple(params) if isinstance(params, list) else params)
        else:
            cursor = self._conn.execute(sql)
        return _DictCursor(cursor)

    def executescript(self, sql):
        self._conn.executescript(sql)

    def commit(self):
        self._conn.commit()
        if self._is_turso and hasattr(self._conn, 'sync'):
            try:
                self._conn.sync()
            except (ValueError, Exception):
                pass  # Remote-only mode doesn't support sync

    def close(self):
        self._conn.close()

    def sync(self):
        """Sync embedded replica with remote (Turso only)."""
        if self._is_turso and hasattr(self._conn, 'sync'):
            try:
                self._conn.sync()
            except (ValueError, Exception):
                pass  # Remote-only mode doesn't support sync


def init_db(db_path: str, turso_url: str | None = None, turso_token: str | None = None) -> DBConnection:
    """Initialize database via libsql — Turso cloud when credentials provided, local libsql otherwise."""
    if turso_url and turso_token:
        conn = libsql.connect(turso_url, auth_token=turso_token)
        is_turso = True
    else:
        conn = libsql.connect(db_path)
        is_turso = False

    wrapped = DBConnection(conn, is_turso=is_turso)
    # Run schema statement by statement (libsql doesn't support executescript)
    for statement in SCHEMA.split(";"):
        statement = statement.strip()
        if statement:
            try:
                wrapped.execute(statement)
            except Exception:
                pass  # IF NOT EXISTS handles duplicates
    wrapped.commit()
    return wrapped


def _serialize_value(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return v


def _row_to_dict(row) -> dict:
    """Convert a row to dict."""
    if isinstance(row, dict):
        return row
    return dict(row)


def insert_row(conn: DBConnection, table: str, data: dict, or_replace: bool = False) -> int:
    _validate_table(table)
    data = {k: _serialize_value(v) for k, v in data.items()}
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    verb = "INSERT OR REPLACE" if or_replace else "INSERT"
    cursor = conn.execute(
        f"{verb} INTO {table} ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cursor.lastrowid


def query_rows(
    conn: DBConnection,
    table: str,
    where: dict | None = None,
    order_by: str = "id DESC",
    limit: int | None = None,
) -> list[dict]:
    _validate_table(table)
    _validate_order_by(order_by)
    sql = f"SELECT * FROM {table}"
    params = []
    if where:
        clauses = []
        for k, v in where.items():
            if k not in _ALLOWED_COLUMNS:
                raise ValueError(f"Invalid column in WHERE: {k}")
            clauses.append(f"{k} = ?")
            params.append(v)
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY {order_by}"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_dict(row) for row in rows]


def update_row(conn: DBConnection, table: str, row_id: int, data: dict):
    _validate_table(table)
    data = {k: _serialize_value(v) for k, v in data.items()}
    sets = ", ".join(f"{k} = ?" for k in data.keys())
    conn.execute(
        f"UPDATE {table} SET {sets} WHERE id = ?",
        tuple([*data.values(), row_id]),
    )
    conn.commit()


def count_rows(conn: DBConnection, table: str, where: dict | None = None) -> int:
    _validate_table(table)
    sql = f"SELECT COUNT(*) as cnt FROM {table}"
    params = []
    if where:
        clauses = []
        for k, v in where.items():
            if k not in _ALLOWED_COLUMNS:
                raise ValueError(f"Invalid column in WHERE: {k}")
            clauses.append(f"{k} = ?")
            params.append(v)
        sql += " WHERE " + " AND ".join(clauses)
    result = conn.execute(sql, tuple(params)).fetchone()
    return result["cnt"]


def rows_since(
    conn: DBConnection,
    table: str,
    since: str,
    date_col: str = "created_at",
) -> list[dict]:
    _validate_table(table)
    if date_col not in _ALLOWED_COLUMNS:
        raise ValueError(f"Invalid date column: {date_col}")
    sql = f"SELECT * FROM {table} WHERE {date_col} >= ? ORDER BY {date_col} DESC"
    rows = conn.execute(sql, (since,)).fetchall()
    return [_row_to_dict(row) for row in rows]


def _migrate_content_pieces(conn: DBConnection):
    """Add devto columns to content_pieces if missing."""
    new_cols = [
        ("devto_article_id", "INTEGER"),
        ("devto_url", "TEXT"),
        ("devto_views", "INTEGER DEFAULT 0"),
        ("devto_reactions", "INTEGER DEFAULT 0"),
        ("devto_comments", "INTEGER DEFAULT 0"),
        ("devto_synced_at", "TEXT"),
    ]
    for col_name, col_type in new_cols:
        try:
            conn.execute(f"ALTER TABLE content_pieces ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass  # Column already exists
    conn.commit()


def init_db_from_config(config) -> DBConnection:
    """Initialize database using config object; picks Turso or local automatically."""
    conn = init_db(
        config.db_path,
        turso_url=config.turso_database_url,
        turso_token=config.turso_auth_token,
    )
    _migrate_content_pieces(conn)
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ALL_TABLES = {
    "seo_pages", "content_pieces", "community_interactions",
    "product_feedback", "run_log", "growth_experiments", "doc_snapshots",
    "agent_memory",
}

# Allowed column names for ORDER BY / WHERE to prevent SQL injection
_ALLOWED_COLUMNS = {
    "id", "slug", "title", "content_type", "status", "created_at", "published_at",
    "word_count", "citations_count", "name", "hypothesis", "metric", "channel",
    "tactic", "duration_days", "concluded_at", "severity", "area", "submitted_at",
    "run_id", "sequence", "command", "started_at", "ended_at", "prev_hash", "hash",
    "success", "keyword", "template_type", "experiment_id", "url", "path",
    "doc_sha256", "content_length", "fetched_at", "changed_from", "thread_url",
    "counterpart", "intent", "question", "sent_at", "body_md",
    "devto_article_id", "devto_url", "devto_views", "devto_reactions",
    "devto_comments", "devto_synced_at",
    "cycle_id", "lesson_type", "key", "insight", "evidence", "confidence",
}


def _validate_table(table: str):
    if table not in ALL_TABLES:
        raise ValueError(f"Invalid table name: {table}")


def _validate_order_by(order_by: str):
    """Validate ORDER BY clause to prevent injection."""
    import re
    # Allow patterns like: "id DESC", "created_at ASC", "id DESC, created_at ASC"
    parts = [p.strip() for p in order_by.split(",")]
    for part in parts:
        match = re.match(r'^(\w+)(?:\s+(ASC|DESC))?$', part, re.IGNORECASE)
        if not match:
            raise ValueError(f"Invalid ORDER BY clause: {order_by}")
        col = match.group(1)
        if col not in _ALLOWED_COLUMNS:
            raise ValueError(f"Invalid column in ORDER BY: {col}")


def exists_similar(conn: DBConnection, table: str, match_cols: dict, threshold: int = 60) -> bool:
    """Check if a similar row already exists based on normalized text matching.

    match_cols: dict of column_name -> value to match against.
    Normalizes text (lowercase, strip punctuation, first `threshold` chars) before comparing.
    Returns True if a similar row exists.
    """
    import re as _re
    _validate_table(table)

    for col, val in match_cols.items():
        if col not in _ALLOWED_COLUMNS:
            raise ValueError(f"Invalid column: {col}")
        if not val:
            continue
        # Normalize the value
        norm = _re.sub(r'[^a-z0-9\s]', '', str(val).strip().lower())
        norm = _re.sub(r'\s+', ' ', norm)[:threshold]
        if not norm:
            continue

        # Check existing rows
        rows = conn.execute(f"SELECT {col} FROM {table}").fetchall()
        for row in rows:
            existing = row[col]
            if not existing:
                continue
            existing_norm = _re.sub(r'[^a-z0-9\s]', '', str(existing).strip().lower())
            existing_norm = _re.sub(r'\s+', ' ', existing_norm)[:threshold]
            if existing_norm == norm:
                return True
    return False


def reset_all_tables(conn: DBConnection):
    """Delete all rows from all tables. Use for clean re-runs."""
    for table in sorted(ALL_TABLES):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
