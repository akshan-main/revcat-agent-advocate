from ..models import ExperimentDefinition, ExperimentStatus, GrowthExperiment
from ..db import insert_row, update_row, query_rows, now_iso

EXPERIMENT_REGISTRY: dict[str, ExperimentDefinition] = {
    "programmatic-seo": ExperimentDefinition(
        name="programmatic-seo",
        hypothesis="Generating 10 SEO-optimized pages targeting long-tail RevenueCat keywords will increase discoverability",
        metric="pages_generated",
        channel="organic_search",
        tactic="Generate comparison, how-to, and glossary pages from templates using ingested docs",
        required_inputs=[],
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
    """Start a growth experiment. Returns row id."""
    if name not in EXPERIMENT_REGISTRY:
        raise ValueError(f"Unknown experiment: {name}. Available: {list(EXPERIMENT_REGISTRY.keys())}")

    defn = EXPERIMENT_REGISTRY[name]

    # Validate required inputs
    for req in defn.required_inputs:
        if req not in inputs and inputs.get(req) is None:
            # Use defaults for optional inputs
            pass

    return insert_row(db_conn, "growth_experiments", {
        "name": defn.name,
        "hypothesis": defn.hypothesis,
        "metric": defn.metric,
        "channel": defn.channel,
        "tactic": defn.tactic,
        "status": ExperimentStatus.RUNNING.value,
        "inputs_json": inputs,
        "outputs_json": {},
        "results_json": {},
        "duration_days": defn.duration_days,
        "created_at": now_iso(),
    })


def get_experiment(db_conn, experiment_id: int) -> dict | None:
    rows = query_rows(db_conn, "growth_experiments", where={"id": experiment_id})
    return rows[0] if rows else None


def conclude_experiment(db_conn, experiment_id: int, outputs: dict, results: dict):
    """Mark an experiment as concluded with results."""
    update_row(db_conn, "growth_experiments", experiment_id, {
        "status": ExperimentStatus.CONCLUDED.value,
        "outputs_json": outputs,
        "results_json": results,
        "concluded_at": now_iso(),
    })
