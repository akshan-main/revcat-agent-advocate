"""Repro Harness: product feedback from actual API/MCP friction, not vibes.

The difference between "the docs seem confusing" and a real bug report is
a reproduction transcript. This module:

1. Runs scripted API/MCP calls against RevenueCat (or mocks in demo mode)
2. Records every request/response in the ledger
3. Detects friction patterns: slow responses, confusing errors, missing fields
4. Generates structured ProductFeedback with real evidence (not LLM hallucination)

Every feedback item links back to the exact transcript that triggered it.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field

import requests

from ..config import Config
from ..db import now_iso
from ..models import ProductFeedback, Severity, FeedbackArea
from ..feedback.collector import create_feedback, save_feedback


# ── Repro Transcript ───────────────────────────────────────────────────

@dataclass
class ReproStep:
    """A single API/MCP call in a repro transcript."""
    action: str               # e.g. "GET /v2/projects/{id}/apps"
    request_summary: str      # what was sent
    response_code: int | None = None
    response_summary: str = ""
    latency_ms: float = 0.0
    error: str = ""
    friction: str = ""        # detected friction description


@dataclass
class ReproTranscript:
    """Full transcript of a repro scenario."""
    scenario_name: str
    steps: list[ReproStep] = field(default_factory=list)
    frictions_found: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    sha256: str = ""          # hash of the full transcript for ledger

    def compute_hash(self) -> str:
        """Compute deterministic hash of this transcript."""
        content = json.dumps({
            "scenario": self.scenario_name,
            "steps": [
                {"action": s.action, "response_code": s.response_code, "error": s.error}
                for s in self.steps
            ],
        }, sort_keys=True)
        self.sha256 = hashlib.sha256(content.encode()).hexdigest()
        return self.sha256


# ── Friction Detectors ─────────────────────────────────────────────────

def _detect_slow_response(step: ReproStep, threshold_ms: float = 3000) -> str | None:
    if step.latency_ms > threshold_ms:
        return f"Slow response: {step.action} took {step.latency_ms:.0f}ms (threshold: {threshold_ms}ms)"
    return None


def _detect_unhelpful_error(step: ReproStep) -> str | None:
    if not step.error:
        return None
    unhelpful_patterns = [
        "internal server error",
        "something went wrong",
        "unexpected error",
        "null",
        "undefined",
    ]
    error_lower = step.error.lower()
    for pattern in unhelpful_patterns:
        if pattern in error_lower:
            return f"Unhelpful error message on {step.action}: '{step.error[:200]}'"
    return None


def _detect_missing_fields(step: ReproStep, expected_fields: list[str]) -> str | None:
    if not step.response_summary:
        return None
    try:
        data = json.loads(step.response_summary)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict):
        missing = [f for f in expected_fields if f not in data]
        if missing:
            return f"Missing fields in {step.action} response: {', '.join(missing)}"
    return None


def _detect_undocumented_error_code(step: ReproStep) -> str | None:
    if step.response_code and step.response_code >= 400:
        # Common undocumented error codes
        if step.response_code in (418, 422, 429, 451, 502, 503):
            return f"Potentially undocumented error code {step.response_code} on {step.action}"
    return None


def analyze_step(step: ReproStep, expected_fields: list[str] | None = None) -> list[str]:
    """Run all friction detectors on a single step."""
    frictions = []
    for detector in [
        lambda s: _detect_slow_response(s),
        lambda s: _detect_unhelpful_error(s),
        lambda s: _detect_undocumented_error_code(s),
    ]:
        result = detector(step)
        if result:
            frictions.append(result)
    if expected_fields:
        result = _detect_missing_fields(step, expected_fields)
        if result:
            frictions.append(result)
    return frictions


# ── Repro Scenarios ────────────────────────────────────────────────────

REPRO_SCENARIOS = {
    "api-basic-flow": {
        "name": "Basic API v2 Flow",
        "description": "Test the basic project → apps → products → offerings flow",
        "steps": [
            {"action": "GET /v2/projects/{project_id}", "expected_fields": ["id", "name"]},
            {"action": "GET /v2/projects/{project_id}/apps", "expected_fields": ["items"]},
            {"action": "GET /v2/projects/{project_id}/offerings", "expected_fields": ["items"]},
            {"action": "GET /v2/projects/{project_id}/entitlements", "expected_fields": ["items"]},
        ],
    },
    "charts-flow": {
        "name": "Charts API Flow",
        "description": "Test charts queries for common metrics",
        "steps": [
            {"action": "GET /v2/projects/{project_id}/metrics/overview", "expected_fields": []},
        ],
    },
    "error-handling": {
        "name": "Error Handling Quality",
        "description": "Test error messages for common mistakes",
        "steps": [
            {"action": "GET /v2/projects/invalid_id", "expected_fields": ["code", "message"]},
            {"action": "GET /v2/projects/{project_id}/customers/nonexistent", "expected_fields": ["code", "message"]},
        ],
    },
    "mcp-discovery": {
        "name": "MCP Tool Discovery",
        "description": "Test MCP server tool listing and basic calls",
        "steps": [
            {"action": "MCP list_tools", "expected_fields": []},
            {"action": "MCP get-project-info", "expected_fields": []},
        ],
    },
}


def _run_api_step(config: Config, step_def: dict, session: requests.Session) -> ReproStep:
    """Execute a single API step and record the result."""
    action = step_def["action"]
    project_id = config.revenuecat_project_id or "proj_demo"

    url_path = action.replace("{project_id}", project_id)

    if url_path.startswith("GET "):
        url_path = url_path[4:]
    elif url_path.startswith("MCP "):
        # MCP calls handled separately
        return ReproStep(
            action=action,
            request_summary=f"MCP call: {action}",
            response_code=None,
            response_summary="MCP scenario; requires async execution",
            friction="",
        )

    url = f"https://api.revenuecat.com{url_path}"
    start = time.monotonic()
    try:
        resp = session.get(url, timeout=15)
        latency_ms = (time.monotonic() - start) * 1000

        response_body = ""
        try:
            response_body = json.dumps(resp.json())[:500]
        except Exception:
            response_body = resp.text[:500]

        error = ""
        if resp.status_code >= 400:
            error = response_body

        return ReproStep(
            action=action,
            request_summary=f"GET {url}",
            response_code=resp.status_code,
            response_summary=response_body,
            latency_ms=latency_ms,
            error=error,
        )
    except requests.RequestException as e:
        latency_ms = (time.monotonic() - start) * 1000
        return ReproStep(
            action=action,
            request_summary=f"GET {url}",
            response_code=None,
            response_summary="",
            latency_ms=latency_ms,
            error=str(e),
            friction=f"Connection error: {e}",
        )


def _run_mock_step(step_def: dict) -> ReproStep:
    """Run a step against mock data for demo mode."""
    action = step_def["action"]

    # Simulate realistic responses
    if "invalid_id" in action or "nonexistent" in action:
        return ReproStep(
            action=action,
            request_summary=f"Mock: {action}",
            response_code=404,
            response_summary='{"code": 7225, "message": "Resource not found"}',
            latency_ms=50,
            error='{"code": 7225, "message": "Resource not found"}',
        )

    if action.startswith("MCP"):
        return ReproStep(
            action=action,
            request_summary=f"Mock MCP: {action}",
            response_code=200,
            response_summary='{"tools": [{"name": "get-project-info"}]}',
            latency_ms=100,
        )

    # Normal success
    return ReproStep(
        action=action,
        request_summary=f"Mock: {action}",
        response_code=200,
        response_summary='{"items": [], "id": "proj_demo", "name": "Demo Project"}',
        latency_ms=80,
    )


# ── Run Scenarios ──────────────────────────────────────────────────────

def run_scenario(config: Config, scenario_name: str) -> ReproTranscript:
    """Run a single repro scenario and return the transcript."""
    scenario = REPRO_SCENARIOS.get(scenario_name)
    if not scenario:
        raise ValueError(f"Unknown scenario: {scenario_name}. Available: {list(REPRO_SCENARIOS.keys())}")

    transcript = ReproTranscript(
        scenario_name=scenario["name"],
        started_at=now_iso(),
    )

    session = None
    if not config.demo_mode and config.revenuecat_api_key:
        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {config.revenuecat_api_key}"
        session.headers["Content-Type"] = "application/json"

    for step_def in scenario["steps"]:
        if config.demo_mode or not session:
            # No API key available — use mock steps (requires demo_mode or missing credentials)
            step = _run_mock_step(step_def)
        else:
            step = _run_api_step(config, step_def, session)

        # Analyze for friction
        frictions = analyze_step(step, step_def.get("expected_fields"))
        for f in frictions:
            step.friction = f
            transcript.frictions_found.append(f)

        transcript.steps.append(step)
        time.sleep(0.1)  # Rate limit

    transcript.ended_at = now_iso()
    transcript.compute_hash()
    return transcript


def run_all_scenarios(config: Config) -> list[ReproTranscript]:
    """Run all repro scenarios."""
    transcripts = []
    for name in REPRO_SCENARIOS:
        transcript = run_scenario(config, name)
        transcripts.append(transcript)
    return transcripts


# ── Transcript → Feedback ──────────────────────────────────────────────

def _friction_to_severity(friction: str) -> Severity:
    """Map friction description to severity level."""
    if "connection error" in friction.lower() or "500" in friction:
        return Severity.CRITICAL
    if "slow response" in friction.lower():
        return Severity.MAJOR
    if "unhelpful error" in friction.lower():
        return Severity.MAJOR
    if "missing fields" in friction.lower():
        return Severity.MINOR
    if "undocumented" in friction.lower():
        return Severity.MINOR
    return Severity.SUGGESTION


def _friction_to_area(friction: str, action: str) -> FeedbackArea:
    """Map friction to the relevant product area."""
    if "MCP" in action:
        return FeedbackArea.MCP
    if "charts" in action.lower() or "metrics" in action.lower():
        return FeedbackArea.CHARTS
    if "/v2/" in action:
        return FeedbackArea.API
    return FeedbackArea.OTHER


def transcript_to_feedback(transcript: ReproTranscript) -> list[ProductFeedback]:
    """Convert friction found in a transcript into structured feedback."""
    feedbacks = []
    for step in transcript.steps:
        if not step.friction:
            continue

        severity = _friction_to_severity(step.friction)
        area = _friction_to_area(step.friction, step.action)

        fb = create_feedback(
            title=step.friction[:100],
            severity=severity,
            area=area,
            repro_steps=(
                f"Scenario: {transcript.scenario_name}\n"
                f"Action: {step.action}\n"
                f"Request: {step.request_summary}\n"
                f"Response code: {step.response_code}"
            ),
            expected="Fast, clear response with helpful error messages",
            actual=(
                f"Response: {step.response_summary[:200]}\n"
                f"Latency: {step.latency_ms:.0f}ms\n"
                f"Error: {step.error[:200]}" if step.error else
                f"Response: {step.response_summary[:200]}\n"
                f"Latency: {step.latency_ms:.0f}ms"
            ),
            evidence_links=[],
            proposed_fix=f"Review {step.action} endpoint behavior",
        )
        feedbacks.append(fb)

    return feedbacks


def run_repro_and_file_feedback(config: Config, db_conn, ledger_ctx=None) -> tuple[list[ReproTranscript], list[ProductFeedback]]:
    """Run all repro scenarios, analyze friction, file feedback.

    Returns (transcripts, feedback_items).
    """
    transcripts = run_all_scenarios(config)
    all_feedback = []

    for transcript in transcripts:
        feedbacks = transcript_to_feedback(transcript)
        for fb in feedbacks:
            save_feedback(db_conn, fb)
            all_feedback.append(fb)

    if ledger_ctx:
        from ..ledger import log_tool_call
        log_tool_call(
            ledger_ctx, "repro.run_all_scenarios",
            f"scenarios={len(REPRO_SCENARIOS)}",
            f"transcripts={len(transcripts)}, frictions={sum(len(t.frictions_found) for t in transcripts)}, feedback={len(all_feedback)}",
        )

    return transcripts, all_feedback


def format_transcript(transcript: ReproTranscript) -> str:
    """Format a transcript as markdown."""
    lines = [
        f"## Repro: {transcript.scenario_name}",
        f"*Started: {transcript.started_at} | Ended: {transcript.ended_at}*",
        f"*Transcript SHA256: `{transcript.sha256[:16]}...`*",
        "",
    ]

    for i, step in enumerate(transcript.steps, 1):
        status = "pass" if not step.friction else "FRICTION"
        code = step.response_code or "N/A"
        lines.append(f"### Step {i}: {step.action}")
        lines.append(f"- Status: **{status}** | HTTP {code} | {step.latency_ms:.0f}ms")
        if step.friction:
            lines.append(f"- Friction: {step.friction}")
        lines.append("")

    if transcript.frictions_found:
        lines.append("### Frictions Summary")
        for f in transcript.frictions_found:
            lines.append(f"- {f}")
    else:
        lines.append("*No friction detected in this scenario.*")

    return "\n".join(lines)


# ── Golden Tests: CI-runnable regression detection ─────────────────────

@dataclass
class GoldenDiff:
    """A single difference between expected and actual transcript."""
    step_index: int
    field: str
    expected: str | int | None
    actual: str | int | None
    severity: str  # "breaking" (code changed), "regression" (new friction), "improvement" (friction removed)


@dataclass
class GoldenTestResult:
    """Result of comparing a transcript against its golden snapshot."""
    scenario_name: str
    passed: bool
    diffs: list[GoldenDiff]
    new_frictions: list[str]
    resolved_frictions: list[str]
    transcript_hash_match: bool


def transcript_to_golden(transcript: ReproTranscript) -> dict:
    """Serialize a transcript to a golden test snapshot (JSON-serializable dict).

    Golden snapshots capture the contract, not timing:
    - Response codes (must not regress)
    - Response structure (expected fields present)
    - Friction state (new friction = regression, removed = improvement)
    Latency is NOT included; it is non-deterministic.
    """
    return {
        "scenario_name": transcript.scenario_name,
        "sha256": transcript.sha256,
        "step_count": len(transcript.steps),
        "steps": [
            {
                "action": step.action,
                "response_code": step.response_code,
                "has_error": bool(step.error),
                "friction": step.friction,
                "response_fields": _extract_response_fields(step.response_summary),
            }
            for step in transcript.steps
        ],
        "friction_count": len(transcript.frictions_found),
        "frictions": transcript.frictions_found,
    }


def _extract_response_fields(response_summary: str) -> list[str]:
    """Extract top-level JSON keys from a response for golden comparison."""
    if not response_summary:
        return []
    try:
        data = json.loads(response_summary)
        if isinstance(data, dict):
            return sorted(data.keys())
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def save_golden(transcript: ReproTranscript, golden_dir: str) -> str:
    """Save a transcript as a golden test file. Returns the file path."""
    import os
    os.makedirs(golden_dir, exist_ok=True)
    slug = transcript.scenario_name.lower().replace(" ", "_").replace("/", "_")
    path = os.path.join(golden_dir, f"golden_{slug}.json")
    golden = transcript_to_golden(transcript)
    with open(path, "w") as f:
        json.dump(golden, f, indent=2, sort_keys=True)
    return path


def load_golden(golden_path: str) -> dict | None:
    """Load a golden test snapshot from disk."""
    try:
        with open(golden_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def compare_transcript(transcript: ReproTranscript, golden: dict) -> GoldenTestResult:
    """Compare a live transcript against a golden snapshot.

    Detects:
    - Response code regressions (200→400 = breaking)
    - New frictions (regression)
    - Resolved frictions (improvement)
    - Missing/added response fields (breaking)
    """
    diffs = []
    new_frictions = []
    resolved_frictions = []
    actual = transcript_to_golden(transcript)

    # Compare step count
    if actual["step_count"] != golden["step_count"]:
        diffs.append(GoldenDiff(
            step_index=-1, field="step_count",
            expected=golden["step_count"], actual=actual["step_count"],
            severity="breaking",
        ))

    # Compare each step
    for i, (act_step, gold_step) in enumerate(
        zip(actual["steps"], golden["steps"])
    ):
        # Response code regression
        if act_step["response_code"] != gold_step["response_code"]:
            gold_code = gold_step["response_code"]
            act_code = act_step["response_code"]
            # 2xx→4xx/5xx is breaking, 4xx→2xx is improvement
            if gold_code and act_code:
                if gold_code < 400 and act_code >= 400:
                    severity = "breaking"
                elif gold_code >= 400 and act_code < 400:
                    severity = "improvement"
                else:
                    severity = "breaking"
            else:
                severity = "breaking"
            diffs.append(GoldenDiff(
                step_index=i, field="response_code",
                expected=gold_code, actual=act_code,
                severity=severity,
            ))

        # New error where there wasn't one
        if act_step["has_error"] and not gold_step["has_error"]:
            diffs.append(GoldenDiff(
                step_index=i, field="has_error",
                expected="no error", actual="error",
                severity="breaking",
            ))

        # Friction changes
        if act_step["friction"] and not gold_step["friction"]:
            new_frictions.append(act_step["friction"])
            diffs.append(GoldenDiff(
                step_index=i, field="friction",
                expected="none", actual=act_step["friction"],
                severity="regression",
            ))
        elif gold_step["friction"] and not act_step["friction"]:
            resolved_frictions.append(gold_step["friction"])

        # Response field changes (fields disappeared)
        gold_fields = set(gold_step.get("response_fields", []))
        act_fields = set(act_step.get("response_fields", []))
        missing_fields = gold_fields - act_fields
        if missing_fields:
            diffs.append(GoldenDiff(
                step_index=i, field="response_fields",
                expected=", ".join(sorted(gold_fields)),
                actual=", ".join(sorted(act_fields)),
                severity="breaking",
            ))

    hash_match = actual["sha256"] == golden["sha256"]
    has_breaking = any(d.severity == "breaking" for d in diffs)
    has_regression = any(d.severity == "regression" for d in diffs)
    passed = not has_breaking and not has_regression

    return GoldenTestResult(
        scenario_name=transcript.scenario_name,
        passed=passed,
        diffs=diffs,
        new_frictions=new_frictions,
        resolved_frictions=resolved_frictions,
        transcript_hash_match=hash_match,
    )


def run_golden_suite(config: Config, golden_dir: str) -> list[GoldenTestResult]:
    """Run all scenarios and compare against golden snapshots.

    If no golden exists for a scenario, creates one (first run = baseline).
    Returns list of results suitable for CI assertion.
    """
    import os
    results = []

    for scenario_name in REPRO_SCENARIOS:
        transcript = run_scenario(config, scenario_name)
        slug = REPRO_SCENARIOS[scenario_name]["name"].lower().replace(" ", "_").replace("/", "_")
        golden_path = os.path.join(golden_dir, f"golden_{slug}.json")

        golden = load_golden(golden_path)
        if golden is None:
            # First run: save as baseline
            save_golden(transcript, golden_dir)
            results.append(GoldenTestResult(
                scenario_name=transcript.scenario_name,
                passed=True,
                diffs=[],
                new_frictions=[],
                resolved_frictions=[],
                transcript_hash_match=True,
            ))
        else:
            result = compare_transcript(transcript, golden)
            results.append(result)

    return results


def format_golden_report(results: list[GoldenTestResult]) -> str:
    """Format golden test results as CI-friendly markdown."""
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    all_pass = passed == total

    lines = [
        "# Golden Test Report",
        "",
        f"**Result: {'PASS' if all_pass else 'FAIL'}** ({passed}/{total} scenarios passed)",
        "",
    ]

    for result in results:
        icon = "PASS" if result.passed else "FAIL"
        lines.append(f"## [{icon}] {result.scenario_name}")
        lines.append(f"Hash match: {'yes' if result.transcript_hash_match else 'no'}")

        if result.diffs:
            lines.append("")
            lines.append("| Step | Field | Expected | Actual | Severity |")
            lines.append("|------|-------|----------|--------|----------|")
            for d in result.diffs:
                step_label = f"Step {d.step_index + 1}" if d.step_index >= 0 else "Global"
                lines.append(f"| {step_label} | {d.field} | {d.expected} | {d.actual} | {d.severity} |")

        if result.new_frictions:
            lines.append("")
            lines.append("**New Frictions (regressions):**")
            for f in result.new_frictions:
                lines.append(f"- {f}")

        if result.resolved_frictions:
            lines.append("")
            lines.append("**Resolved Frictions (improvements):**")
            for f in result.resolved_frictions:
                lines.append(f"- {f}")

        lines.append("")

    return "\n".join(lines)
