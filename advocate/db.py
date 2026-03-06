import json
import sqlite3
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
    sources_json TEXT,
    verification_json TEXT,
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
    """Unified database connection wrapping either sqlite3 or libsql (Turso)."""

    def __init__(self, conn, is_turso: bool = False):
        self._conn = conn
        self._is_turso = is_turso

    def execute(self, sql, params=None):
        if params:
            cursor = self._conn.execute(sql, tuple(params) if isinstance(params, list) else params)
        else:
            cursor = self._conn.execute(sql)
        if self._is_turso:
            return _DictCursor(cursor)
        return cursor

    def executescript(self, sql):
        self._conn.executescript(sql)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def sync(self):
        """Sync embedded replica with remote (Turso only)."""
        if self._is_turso and hasattr(self._conn, 'sync'):
            self._conn.sync()


def init_db(db_path: str, turso_url: str | None = None, turso_token: str | None = None) -> DBConnection:
    """Initialize database: uses Turso cloud if credentials provided, else local SQLite."""
    if turso_url and turso_token:
        import libsql_experimental as libsql
        conn = libsql.connect(turso_url, auth_token=turso_token)
        wrapped = DBConnection(conn, is_turso=True)
        # Run schema (executescript splits statements)
        for statement in SCHEMA.split(";"):
            statement = statement.strip()
            if statement:
                try:
                    wrapped.execute(statement)
                except Exception:
                    pass  # IF NOT EXISTS handles duplicates
        wrapped.commit()
        return wrapped
    elif db_path == ":memory:" or not turso_url:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        wrapped = DBConnection(conn, is_turso=False)
        return wrapped
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        return DBConnection(conn, is_turso=False)


def _serialize_value(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return v


def _row_to_dict(row) -> dict:
    """Convert a row to dict, handling both sqlite3.Row and plain dict."""
    if isinstance(row, dict):
        return row
    return dict(row)


def insert_row(conn: DBConnection, table: str, data: dict) -> int:
    data = {k: _serialize_value(v) for k, v in data.items()}
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    cursor = conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
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
    sql = f"SELECT * FROM {table}"
    params = []
    if where:
        clauses = []
        for k, v in where.items():
            clauses.append(f"{k} = ?")
            params.append(v)
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY {order_by}"
    if limit:
        sql += f" LIMIT {limit}"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_dict(row) for row in rows]


def update_row(conn: DBConnection, table: str, row_id: int, data: dict):
    data = {k: _serialize_value(v) for k, v in data.items()}
    sets = ", ".join(f"{k} = ?" for k in data.keys())
    conn.execute(
        f"UPDATE {table} SET {sets} WHERE id = ?",
        tuple([*data.values(), row_id]),
    )
    conn.commit()


def count_rows(conn: DBConnection, table: str, where: dict | None = None) -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    params = []
    if where:
        clauses = []
        for k, v in where.items():
            clauses.append(f"{k} = ?")
            params.append(v)
        sql += " WHERE " + " AND ".join(clauses)
    result = conn.execute(sql, tuple(params)).fetchone()
    if isinstance(result, dict):
        return list(result.values())[0]
    return result[0]


def rows_since(
    conn: DBConnection,
    table: str,
    since: str,
    date_col: str = "created_at",
) -> list[dict]:
    sql = f"SELECT * FROM {table} WHERE {date_col} >= ? ORDER BY {date_col} DESC"
    rows = conn.execute(sql, (since,)).fetchall()
    return [_row_to_dict(row) for row in rows]


def init_db_from_config(config) -> DBConnection:
    """Initialize database using config object; picks Turso or local automatically."""
    return init_db(
        config.db_path,
        turso_url=config.turso_database_url,
        turso_token=config.turso_auth_token,
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
