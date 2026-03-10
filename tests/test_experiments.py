import json

import pytest

from advocate.growth.experiments import (
    EXPERIMENT_REGISTRY, start_experiment, get_experiment,
    record_experiment_output, conclude_experiment,
)


def test_registry_has_expected_experiments():
    assert "programmatic-seo" in EXPERIMENT_REGISTRY
    assert "content-series" in EXPERIMENT_REGISTRY
    assert "community-blitz" in EXPERIMENT_REGISTRY
    assert "integration-showcase" in EXPERIMENT_REGISTRY


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


def test_conclude_requires_engagement_data(db_conn):
    """Cannot conclude without real engagement metrics."""
    exp_id = start_experiment(db_conn, "programmatic-seo", {})
    with pytest.raises(ValueError, match="measured engagement data"):
        conclude_experiment(db_conn, exp_id, {"pages_generated": 10})


def test_conclude_with_engagement_data(db_conn):
    """Can conclude when real engagement data is provided."""
    exp_id = start_experiment(db_conn, "programmatic-seo", {})
    conclude_experiment(db_conn, exp_id, {
        "page_views": 1200,
        "clicks": 45,
        "pages_generated": 10,
    })

    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "concluded"
    assert exp["concluded_at"] is not None


def test_experiment_lifecycle(db_conn):
    # Start
    exp_id = start_experiment(db_conn, "content-series", {"theme": "MCP", "count": 5})
    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "running"

    # Record output — stays running
    record_experiment_output(db_conn, exp_id, {"posts": 5}, {"posts_published": 5})
    exp = get_experiment(db_conn, exp_id)
    assert exp["status"] == "running"

    # Conclude with engagement data
    conclude_experiment(db_conn, exp_id, {"page_views": 500, "posts_published": 5})
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
