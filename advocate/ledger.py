import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone

from .config import Config
from .db import insert_row, now_iso, query_rows
from .models import (
    ChainVerification,
    LedgerOutputs,
    LedgerSource,
    LedgerToolCall,
    RunEntry,
    VerificationResult,
)


class RunContext:
    """Context manager for tracking a single agent run."""

    def __init__(self, db_conn: sqlite3.Connection, command: str, inputs: dict, config: Config):
        self.db_conn = db_conn
        self.config = config
        self.command = command
        self.inputs = inputs
        self.started_at = now_iso()
        self.tool_calls: list[LedgerToolCall] = []
        self.sources_used: list[LedgerSource] = []

        # Determine sequence and prev_hash
        last = query_rows(db_conn, "run_log", order_by="sequence DESC", limit=1)
        if last:
            self.sequence = last[0]["sequence"] + 1
            self.prev_hash = last[0]["hash"]
        else:
            self.sequence = 1
            self.prev_hash = "GENESIS"

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        import random
        suffix = random.randint(1000, 9999)
        self.run_id = f"run_{ts}_{suffix}_{command.replace('-', '_')}"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # If not finalized, finalize with failure
        if not hasattr(self, "_finalized"):
            finalize_run(
                self,
                self.config,
                self.db_conn,
                outputs=LedgerOutputs(),
                verification=None,
                success=exc_type is None,
            )
        return False


def start_run(db_conn: sqlite3.Connection, command: str, inputs: dict, config: Config) -> RunContext:
    return RunContext(db_conn, command, inputs, config)


def log_tool_call(ctx: RunContext, tool: str, params_summary: str = "", result_summary: str = ""):
    ctx.tool_calls.append(LedgerToolCall(
        tool=tool,
        params_summary=params_summary,
        result_summary=result_summary,
    ))


def log_source(ctx: RunContext, url: str, doc_sha256: str = "", snippet_hashes: list[str] | None = None):
    ctx.sources_used.append(LedgerSource(
        url=url,
        doc_sha256=doc_sha256,
        sections_cited=1,
        snippet_hashes=snippet_hashes or [],
    ))


def _canonical_json(entry: RunEntry) -> str:
    data = entry.model_dump(exclude={"hash", "signature"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _compute_hash(prev_hash: str, canonical: str) -> str:
    payload = prev_hash.encode() + canonical.encode()
    return hashlib.sha256(payload).hexdigest()


def _compute_signature(hmac_key: str, hash_value: str) -> str:
    return hmac.new(
        hmac_key.encode(),
        hash_value.encode(),
        hashlib.sha256,
    ).hexdigest()


def finalize_run(
    ctx: RunContext,
    config: Config,
    db_conn: sqlite3.Connection,
    outputs: LedgerOutputs,
    verification: VerificationResult | None,
    success: bool = True,
) -> RunEntry:
    ctx._finalized = True

    entry = RunEntry(
        run_id=ctx.run_id,
        sequence=ctx.sequence,
        prev_hash=ctx.prev_hash,
        command=ctx.command,
        started_at=ctx.started_at,
        ended_at=now_iso(),
        inputs=ctx.inputs,
        sources_used=ctx.sources_used,
        tool_calls=ctx.tool_calls,
        outputs=outputs,
        verification=verification,
        success=success,
    )

    # Compute hash chain
    canonical = _canonical_json(entry)
    entry.hash = _compute_hash(ctx.prev_hash, canonical)

    # Optional HMAC signature
    if config.ledger_hmac_key:
        entry.signature = _compute_signature(config.ledger_hmac_key, entry.hash)

    # Store in DB
    insert_row(db_conn, "run_log", {
        "run_id": entry.run_id,
        "sequence": entry.sequence,
        "command": entry.command,
        "started_at": entry.started_at,
        "ended_at": entry.ended_at,
        "inputs_json": entry.inputs,
        "sources_json": [s.model_dump() for s in entry.sources_used],
        "tool_calls_json": [t.model_dump() for t in entry.tool_calls],
        "outputs_json": entry.outputs.model_dump(),
        "verification_json": entry.verification.model_dump() if entry.verification else None,
        "prev_hash": entry.prev_hash,
        "hash": entry.hash,
        "signature": entry.signature,
        "success": 1 if entry.success else 0,
    })

    # Write JSON file
    runs_dir = config.runs_dir
    os.makedirs(runs_dir, exist_ok=True)
    run_path = os.path.join(runs_dir, f"{entry.run_id}.json")
    with open(run_path, "w") as f:
        json.dump(entry.model_dump(), f, indent=2)

    return entry


def verify_chain(db_conn: sqlite3.Connection, config: Config | None = None) -> ChainVerification:
    rows = query_rows(db_conn, "run_log", order_by="sequence ASC")

    if not rows:
        return ChainVerification(valid=True, total_entries=0)

    breaks = []
    hmac_ok = True if (config and config.ledger_hmac_key) else None

    expected_prev = "GENESIS"
    for row in rows:
        # Reconstruct the entry to recompute hash
        entry = RunEntry(
            run_id=row["run_id"],
            sequence=row["sequence"],
            prev_hash=row["prev_hash"],
            command=row["command"],
            started_at=row["started_at"],
            ended_at=row["ended_at"] or "",
            inputs=json.loads(row["inputs_json"]) if row["inputs_json"] else {},
            sources_used=[LedgerSource(**s) for s in (json.loads(row["sources_json"]) if row["sources_json"] else [])],
            tool_calls=[LedgerToolCall(**t) for t in (json.loads(row["tool_calls_json"]) if row["tool_calls_json"] else [])],
            outputs=LedgerOutputs(**(json.loads(row["outputs_json"]) if row["outputs_json"] else {})),
            verification=VerificationResult(**(json.loads(row["verification_json"]))) if row["verification_json"] else None,
            success=bool(row["success"]),
        )

        # Check prev_hash linkage
        if row["prev_hash"] != expected_prev:
            breaks.append(row["sequence"])

        # Recompute hash
        canonical = _canonical_json(entry)
        expected_hash = _compute_hash(row["prev_hash"], canonical)
        if row["hash"] != expected_hash:
            breaks.append(row["sequence"])

        # Check HMAC if configured
        if config and config.ledger_hmac_key and row["signature"]:
            expected_sig = _compute_signature(config.ledger_hmac_key, row["hash"])
            if row["signature"] != expected_sig:
                hmac_ok = False

        expected_prev = row["hash"]

    return ChainVerification(
        valid=len(breaks) == 0,
        total_entries=len(rows),
        breaks=breaks,
        hmac_verified=hmac_ok,
    )
