import json
import time
from ..models import ExperimentDefinition, ExperimentStatus
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
    "agentic": ExperimentDefinition(
        name="agentic",
        hypothesis="Agent-designed experiment based on autonomous landscape analysis",
        metric="agent_determined",
        channel="agent_determined",
        tactic="Agent autonomously researches the landscape, identifies an opportunity, designs a hypothesis, and executes the experiment",
        required_inputs=[],
        duration_days=7,
    ),
}


def start_experiment(db_conn, name: str, inputs: dict) -> int:
    """Start a growth experiment. Returns row id."""
    if name not in EXPERIMENT_REGISTRY:
        raise ValueError(f"Unknown experiment: {name}. Available: {list(EXPERIMENT_REGISTRY.keys())}")

    defn = EXPERIMENT_REGISTRY[name]

    # Validate required inputs
    for req in defn.required_inputs:
        if req not in inputs and req != "keywords_or_auto":
            inputs[req] = f"auto_{req}"  # Auto-fill with marker so it's traceable

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


def record_experiment_output(db_conn, experiment_id: int, outputs: dict, results: dict):
    """Record experiment outputs. Status stays 'running' — conclusion requires measured engagement data."""
    update_row(db_conn, "growth_experiments", experiment_id, {
        "outputs_json": outputs,
        "results_json": results,
    })


def conclude_experiment(db_conn, experiment_id: int, results: dict):
    """Mark an experiment as concluded with a verdict."""
    update_row(db_conn, "growth_experiments", experiment_id, {
        "status": ExperimentStatus.CONCLUDED.value,
        "results_json": results,
        "concluded_at": now_iso(),
    })


def evaluate_experiment(db_conn, experiment_id: int, config) -> dict:
    """Use Claude to evaluate experiment outputs and generate a scale/kill/iterate verdict.

    Returns dict with: verdict, confidence, reasoning, next_action.
    Also updates the experiment's results_json with the verdict.
    """
    exp = get_experiment(db_conn, experiment_id)
    if not exp:
        raise ValueError(f"Experiment {experiment_id} not found")

    if not config or not config.has_anthropic:
        raise RuntimeError("Anthropic API key required for experiment evaluation. Set ANTHROPIC_API_KEY.")

    import anthropic
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    outputs = exp.get("outputs_json", {})
    results = exp.get("results_json", {})

    prompt = (
        f"Experiment: {exp.get('name')}\n"
        f"Hypothesis: {exp.get('hypothesis')}\n"
        f"Tactic: {exp.get('tactic')}\n"
        f"Target metric: {exp.get('metric')}\n"
        f"Duration: {exp.get('duration_days')} days\n"
        f"Outputs: {json.dumps(outputs, default=str)}\n"
        f"Results so far: {json.dumps(results, default=str)}\n\n"
        "Based on the outputs and results, provide a verdict:\n"
        "- SCALE: Strong signal, invest more resources\n"
        "- KILL: Not working, stop and reallocate\n"
        "- ITERATE: Promising but needs refinement\n\n"
        'Reply with ONLY JSON: {"verdict": "scale|kill|iterate", '
        '"confidence": 0.0-1.0, "reasoning": "one paragraph", '
        '"next_action": "specific next step"}'
    )

    time.sleep(0.3)
    resp = client.messages.create(
        model=config.ai_model,
        max_tokens=500,
        system="You are a growth strategist evaluating experiment results. Be data-driven and honest.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()

    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if m:
            verdict = json.loads(m.group())
        else:
            verdict = {
                "verdict": "iterate",
                "confidence": 0.5,
                "reasoning": text[:300],
                "next_action": "Review manually.",
            }

    # Normalize verdict value
    v = verdict.get("verdict", "iterate").lower()
    if v not in ("scale", "kill", "iterate"):
        v = "iterate"
    verdict["verdict"] = v
    verdict["confidence"] = min(1.0, max(0.0, float(verdict.get("confidence", 0.5))))

    # Merge verdict into results and conclude
    existing_results = exp.get("results_json", {}) or {}
    if isinstance(existing_results, str):
        existing_results = json.loads(existing_results)
    existing_results["verdict"] = verdict["verdict"]
    existing_results["verdict_confidence"] = verdict["confidence"]
    existing_results["verdict_reasoning"] = verdict["reasoning"]
    existing_results["verdict_next_action"] = verdict["next_action"]

    conclude_experiment(db_conn, experiment_id, existing_results)
    return verdict
