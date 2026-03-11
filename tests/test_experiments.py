import json

import pytest

from advocate.growth.experiments import (
    EXPERIMENT_REGISTRY, start_experiment, get_experiment,
    record_experiment_output, conclude_experiment, evaluate_experiment,
)


def test_registry_has_expected_experiments():
    assert "programmatic-seo" in EXPERIMENT_REGISTRY
    assert "content-series" in EXPERIMENT_REGISTRY
    assert "community-blitz" in EXPERIMENT_REGISTRY
    assert "integration-showcase" in EXPERIMENT_REGISTRY
    assert "agentic" in EXPERIMENT_REGISTRY


def test_start_experiment(db_conn):
    exp_id = start_experiment(db_conn, "programmatic-seo", {})
    assert exp_id > 0

    exp = get_experiment(db_conn, exp_id)
    assert exp is not None
    assert exp["name"] == "programmatic-seo"
    assert exp["status"] == "running"


def test_start_unknown_experiment(db_conn):
    with pytest.raises(ValueError, match="Unknown experiment"):
        start_experiment(db_conn, "nonexistent", {})


def test_record_output_keeps_running(db_conn):
    """Recording outputs should NOT conclude the experiment."""
    exp_id = start_experiment(db_conn, "programmatic-seo", {})
    record_experiment_output(db_conn, exp_id, {"pages": 10}, {"pages_generated": 10})

    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "running"  # NOT concluded
    assert exp["concluded_at"] is None
    results = json.loads(exp["results_json"])
    assert results["pages_generated"] == 10


def test_conclude_experiment(db_conn):
    """conclude_experiment sets status to concluded with results."""
    exp_id = start_experiment(db_conn, "programmatic-seo", {})
    conclude_experiment(db_conn, exp_id, {
        "verdict": "scale",
        "verdict_confidence": 0.8,
        "verdict_reasoning": "Strong output.",
        "verdict_next_action": "Double down.",
    })

    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "concluded"
    assert exp["concluded_at"] is not None
    results = json.loads(exp["results_json"])
    assert results["verdict"] == "scale"
    assert results["verdict_confidence"] == 0.8


def test_evaluate_experiment_requires_api_key(db_conn):
    """Without API key, evaluate_experiment raises RuntimeError."""
    exp_id = start_experiment(db_conn, "programmatic-seo", {})
    record_experiment_output(db_conn, exp_id, {"pages_generated": 10}, {})

    with pytest.raises(RuntimeError, match="Anthropic API key required"):
        evaluate_experiment(db_conn, exp_id, config=None)

    # Experiment should still be running (not concluded)
    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "running"


def test_evaluate_experiment_not_found(db_conn):
    """evaluate_experiment raises for nonexistent experiment."""
    with pytest.raises(ValueError, match="not found"):
        evaluate_experiment(db_conn, 9999, config=None)


def test_experiment_lifecycle(db_conn):
    # Start
    exp_id = start_experiment(db_conn, "content-series", {"theme": "MCP", "count": 5})
    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "running"

    # Record output — stays running
    record_experiment_output(db_conn, exp_id, {"posts": 5}, {"posts_published": 5})
    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "running"

    # Manually conclude with verdict (evaluate_experiment requires API key)
    conclude_experiment(db_conn, exp_id, {
        "posts_published": 5,
        "verdict": "iterate",
        "verdict_confidence": 0.7,
        "verdict_reasoning": "Promising series but needs more data.",
        "verdict_next_action": "Measure engagement over next week.",
    })
    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "concluded"


def test_experiment_definition_fields():
    defn = EXPERIMENT_REGISTRY["programmatic-seo"]
    assert defn.name == "programmatic-seo"
    assert defn.hypothesis != ""
    assert defn.metric != ""
    assert defn.channel != ""
    assert defn.tactic != ""
    assert defn.duration_days > 0
