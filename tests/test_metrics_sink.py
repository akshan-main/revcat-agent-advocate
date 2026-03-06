"""Tests for the metrics sink: closed-loop impact measurement."""
from advocate.db import insert_row, now_iso
from advocate.metrics.sink import (
    MetricsContract,
    MetricEvent,
    store_metric_event,
    store_metrics_contract,
    check_stopping_rules,
    generate_impact_report,
    format_impact_report,
    init_metrics_db,
)


def _create_experiment(db_conn, exp_id: int):
    """Helper to insert a growth_experiments row to satisfy FK."""
    insert_row(db_conn, "growth_experiments", {
        "name": f"test-exp-{exp_id}",
        "hypothesis": "test",
        "metric": "test",
        "channel": "test",
        "tactic": "test",
        "status": "running",
        "created_at": now_iso(),
    })


def test_store_metric_event(db_conn):
    init_metrics_db(db_conn)
    event = MetricEvent(
        source="github",
        metric_name="comment_upvotes",
        value=5.0,
        dimensions={"repo": "test/repo"},
    )
    row_id = store_metric_event(db_conn, event)
    assert row_id > 0

    row = db_conn.execute("SELECT * FROM metric_events WHERE id = ?", [row_id]).fetchone()
    assert row["metric_name"] == "comment_upvotes"
    assert row["value"] == 5.0


def test_store_metrics_contract(db_conn):
    init_metrics_db(db_conn)
    _create_experiment(db_conn, 1)
    contract = MetricsContract(
        experiment_id=1,
        primary_metric="page_views",
        primary_target=100.0,
        guardrail_metric="bounce_rate",
        guardrail_threshold=0.8,
        stopping_rule="signal:target_reached",
    )
    row_id = store_metrics_contract(db_conn, contract)
    assert row_id > 0


def test_check_stopping_rules_no_contract(db_conn):
    init_metrics_db(db_conn)
    should_stop, reason = check_stopping_rules(db_conn, 999)
    assert not should_stop
    assert reason == "no_contract"


def test_check_stopping_rules_guardrail_breach(db_conn):
    init_metrics_db(db_conn)
    _create_experiment(db_conn, 1)
    contract = MetricsContract(
        experiment_id=1,
        primary_metric="clicks",
        primary_target=50.0,
        guardrail_metric="spam_reports",
        guardrail_threshold=2.0,
        stopping_rule="time:7d",
    )
    store_metrics_contract(db_conn, contract)

    # Add guardrail events that breach threshold
    for _ in range(3):
        store_metric_event(db_conn, MetricEvent(
            source="manual", metric_name="spam_reports",
            value=1.0, dimensions={}, experiment_id=1,
        ))

    should_stop, reason = check_stopping_rules(db_conn, 1)
    assert should_stop
    assert "guardrail_breached" in reason


def test_check_stopping_rules_target_reached(db_conn):
    init_metrics_db(db_conn)
    _create_experiment(db_conn, 1)  # Gets auto-id 1
    contract = MetricsContract(
        experiment_id=1,
        primary_metric="signups",
        primary_target=10.0,
        guardrail_metric="complaints",
        guardrail_threshold=5.0,
        stopping_rule="signal:target_reached",
    )
    store_metrics_contract(db_conn, contract)

    # Reach target
    store_metric_event(db_conn, MetricEvent(
        source="manual", metric_name="signups",
        value=15.0, dimensions={}, experiment_id=1,
    ))

    should_stop, reason = check_stopping_rules(db_conn, 1)
    assert should_stop
    assert "target_reached" in reason


def test_check_stopping_rules_still_running(db_conn):
    init_metrics_db(db_conn)
    _create_experiment(db_conn, 1)  # Gets auto-id 1
    contract = MetricsContract(
        experiment_id=1,
        primary_metric="clicks",
        primary_target=100.0,
        guardrail_metric="spam",
        guardrail_threshold=10.0,
        stopping_rule="signal:target_reached",
    )
    store_metrics_contract(db_conn, contract)

    store_metric_event(db_conn, MetricEvent(
        source="manual", metric_name="clicks",
        value=5.0, dimensions={}, experiment_id=1,
    ))

    should_stop, reason = check_stopping_rules(db_conn, 1)
    assert not should_stop
    assert reason == "running"


def test_generate_impact_report(db_conn, mock_config):
    init_metrics_db(db_conn)
    report = generate_impact_report(db_conn, mock_config)
    assert report.period == "last_collection"
    assert isinstance(report.learnings, list)
    assert isinstance(report.next_actions, list)


def test_format_impact_report(db_conn, mock_config):
    init_metrics_db(db_conn)
    store_metric_event(db_conn, MetricEvent(
        source="manual", metric_name="test_metric",
        value=42.0, dimensions={},
    ))
    report = generate_impact_report(db_conn, mock_config)
    md = format_impact_report(report)
    assert "Impact Measurement Report" in md
