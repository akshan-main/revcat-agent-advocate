import json

from advocate.config import Config
from advocate.db import insert_row, now_iso
from advocate.ledger import (
    start_run, finalize_run, log_tool_call, log_source,
    verify_chain, _canonical_json, _compute_hash, _compute_signature,
)
from advocate.models import LedgerOutputs, VerificationResult


def _make_config(tmp_path, hmac_key=None):
    return Config(
        runs_dir=str(tmp_path / "runs"),
        _env_file=None,
        ledger_hmac_key=hmac_key,
    )


def test_genesis_entry(db_conn, tmp_path):
    config = _make_config(tmp_path)
    with start_run(db_conn, "test-cmd", {"a": 1}, config) as ctx:
        assert ctx.sequence == 1
        assert ctx.prev_hash == "GENESIS"
        finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)


def test_sequence_increment(db_conn, tmp_path):
    config = _make_config(tmp_path)
    # First run
    with start_run(db_conn, "cmd-1", {}, config) as ctx1:
        entry1 = finalize_run(ctx1, config, db_conn, outputs=LedgerOutputs(), verification=None)

    # Second run
    with start_run(db_conn, "cmd-2", {}, config) as ctx2:
        assert ctx2.sequence == 2
        assert ctx2.prev_hash == entry1.hash
        assert ctx2.prev_hash != "GENESIS"
        finalize_run(ctx2, config, db_conn, outputs=LedgerOutputs(), verification=None)


def test_chain_verification_passes(db_conn, tmp_path):
    config = _make_config(tmp_path)
    for i in range(3):
        with start_run(db_conn, f"cmd-{i}", {"i": i}, config) as ctx:
            log_tool_call(ctx, "tool_a", "param", "result")
            finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)

    chain = verify_chain(db_conn, config)
    assert chain.valid is True
    assert chain.total_entries == 3
    assert chain.breaks == []


def test_chain_detects_tamper(db_conn, tmp_path):
    config = _make_config(tmp_path)
    for i in range(3):
        with start_run(db_conn, f"cmd-{i}", {}, config) as ctx:
            finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)

    # Tamper with entry #2
    db_conn.execute("UPDATE run_log SET hash = 'TAMPERED' WHERE sequence = 2")
    db_conn.commit()

    chain = verify_chain(db_conn, config)
    assert chain.valid is False
    assert 2 in chain.breaks or 3 in chain.breaks


def test_hmac_signature(db_conn, tmp_path):
    config = _make_config(tmp_path, hmac_key="test_secret_key")
    with start_run(db_conn, "signed-cmd", {}, config) as ctx:
        entry = finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)

    assert entry.signature is not None
    assert len(entry.signature) == 64  # hex sha256

    chain = verify_chain(db_conn, config)
    assert chain.valid is True
    assert chain.hmac_verified is True


def test_hmac_wrong_key_fails(db_conn, tmp_path):
    config = _make_config(tmp_path, hmac_key="correct_key")
    with start_run(db_conn, "signed-cmd", {}, config) as ctx:
        finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)

    # Verify with wrong key
    wrong_config = _make_config(tmp_path, hmac_key="wrong_key")
    chain = verify_chain(db_conn, wrong_config)
    assert chain.hmac_verified is False


def test_log_tool_call(db_conn, tmp_path):
    config = _make_config(tmp_path)
    with start_run(db_conn, "test", {}, config) as ctx:
        log_tool_call(ctx, "search", "query=charts", "3 results")
        assert len(ctx.tool_calls) == 1
        assert ctx.tool_calls[0].tool == "search"
        finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)


def test_log_source(db_conn, tmp_path):
    config = _make_config(tmp_path)
    with start_run(db_conn, "test", {}, config) as ctx:
        log_source(ctx, "https://example.com/doc", "sha256abc")
        assert len(ctx.sources_used) == 1
        assert ctx.sources_used[0].url == "https://example.com/doc"
        finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)


def test_run_json_file_written(db_conn, tmp_path):
    config = _make_config(tmp_path)
    with start_run(db_conn, "test", {}, config) as ctx:
        entry = finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)

    import os
    json_path = os.path.join(str(tmp_path / "runs"), f"{entry.run_id}.json")
    assert os.path.exists(json_path)
    with open(json_path) as f:
        data = json.load(f)
    assert data["run_id"] == entry.run_id
    assert data["hash"] == entry.hash


def test_empty_chain_is_valid(db_conn):
    chain = verify_chain(db_conn)
    assert chain.valid is True
    assert chain.total_entries == 0


def test_finalize_sets_ended_at(db_conn, tmp_path):
    config = _make_config(tmp_path)
    with start_run(db_conn, "test", {}, config) as ctx:
        entry = finalize_run(ctx, config, db_conn, outputs=LedgerOutputs(), verification=None)
    assert entry.ended_at != ""


def test_context_manager_auto_finalize(db_conn, tmp_path):
    config = _make_config(tmp_path)
    with start_run(db_conn, "auto", {}, config) as ctx:
        pass  # Don't manually finalize

    # Should have auto-finalized
    rows = db_conn.execute("SELECT * FROM run_log").fetchall()
    assert len(rows) == 1
