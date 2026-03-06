"""Tests for the repro harness: API/MCP friction detection and feedback generation."""
from advocate.feedback.repro import (
    ReproStep,
    ReproTranscript,
    analyze_step,
    run_scenario,
    run_all_scenarios,
    transcript_to_feedback,
    format_transcript,
    run_repro_and_file_feedback,
    _detect_slow_response,
    _detect_unhelpful_error,
    _detect_missing_fields,
    _detect_undocumented_error_code,
    transcript_to_golden,
    save_golden,
    load_golden,
    compare_transcript,
    run_golden_suite,
    format_golden_report,
    GoldenDiff,
    GoldenTestResult,
    REPRO_SCENARIOS,
)
from advocate.models import Severity


def test_detect_slow_response():
    step = ReproStep(action="GET /test", request_summary="test", latency_ms=5000)
    assert _detect_slow_response(step) is not None
    assert "5000" in _detect_slow_response(step)


def test_detect_slow_response_fast():
    step = ReproStep(action="GET /test", request_summary="test", latency_ms=200)
    assert _detect_slow_response(step) is None


def test_detect_unhelpful_error():
    step = ReproStep(action="GET /test", request_summary="test", error="Internal Server Error")
    assert _detect_unhelpful_error(step) is not None


def test_detect_unhelpful_error_helpful():
    step = ReproStep(action="GET /test", request_summary="test", error="Invalid API key: must start with sk_")
    assert _detect_unhelpful_error(step) is None


def test_detect_missing_fields():
    step = ReproStep(
        action="GET /test", request_summary="test",
        response_summary='{"id": "proj_1", "name": "Test"}',
    )
    assert _detect_missing_fields(step, ["id", "name"]) is None
    result = _detect_missing_fields(step, ["id", "name", "apps"])
    assert result is not None
    assert "apps" in result


def test_detect_undocumented_error_code():
    step = ReproStep(action="GET /test", request_summary="test", response_code=422)
    assert _detect_undocumented_error_code(step) is not None

    step_ok = ReproStep(action="GET /test", request_summary="test", response_code=200)
    assert _detect_undocumented_error_code(step_ok) is None


def test_analyze_step_combines_detectors():
    step = ReproStep(
        action="GET /test", request_summary="test",
        response_code=422, latency_ms=5000, error="Internal Server Error",
    )
    frictions = analyze_step(step)
    assert len(frictions) >= 2  # slow + unhelpful error + undocumented code


def test_repro_transcript_hash():
    transcript = ReproTranscript(scenario_name="test")
    transcript.steps.append(ReproStep(action="GET /test", request_summary="test", response_code=200))
    hash1 = transcript.compute_hash()
    assert len(hash1) == 64  # sha256 hex

    # Same steps = same hash
    transcript2 = ReproTranscript(scenario_name="test")
    transcript2.steps.append(ReproStep(action="GET /test", request_summary="test", response_code=200))
    assert transcript2.compute_hash() == hash1


def test_run_scenario_demo_mode(mock_config):
    transcript = run_scenario(mock_config, "api-basic-flow")
    assert transcript.scenario_name == "Basic API v2 Flow"
    assert len(transcript.steps) > 0
    assert transcript.sha256


def test_run_all_scenarios_demo_mode(mock_config):
    transcripts = run_all_scenarios(mock_config)
    assert len(transcripts) == len(REPRO_SCENARIOS)


def test_transcript_to_feedback():
    transcript = ReproTranscript(scenario_name="test")
    transcript.steps.append(ReproStep(
        action="GET /v2/test",
        request_summary="test",
        response_code=200,
        latency_ms=5000,
        friction="Slow response: GET /v2/test took 5000ms",
    ))
    feedbacks = transcript_to_feedback(transcript)
    assert len(feedbacks) == 1
    # "slow response" maps to MAJOR
    assert feedbacks[0].severity in (Severity.MAJOR, Severity.CRITICAL)


def test_transcript_to_feedback_no_friction():
    transcript = ReproTranscript(scenario_name="test")
    transcript.steps.append(ReproStep(
        action="GET /v2/test", request_summary="test",
        response_code=200, latency_ms=100,
    ))
    assert transcript_to_feedback(transcript) == []


def test_run_repro_and_file_feedback(mock_config, db_conn):
    transcripts, feedbacks = run_repro_and_file_feedback(mock_config, db_conn)
    assert len(transcripts) > 0
    # In demo mode, mock responses are clean; feedback may or may not be generated
    assert isinstance(feedbacks, list)


def test_format_transcript():
    transcript = ReproTranscript(
        scenario_name="Test Scenario",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
    )
    transcript.steps.append(ReproStep(
        action="GET /test", request_summary="test",
        response_code=200, latency_ms=50,
    ))
    transcript.compute_hash()
    md = format_transcript(transcript)
    assert "Test Scenario" in md
    assert "Step 1" in md


def test_scenario_names():
    """All scenarios have required fields."""
    for name, scenario in REPRO_SCENARIOS.items():
        assert "name" in scenario
        assert "steps" in scenario
        assert len(scenario["steps"]) > 0


# ── Golden Test Suite ────────────────────────────────────────────────


def _make_transcript(code=200, friction="", error="", response_summary='{"id": "1", "name": "Test"}'):
    """Helper to build a transcript for golden test comparisons."""
    t = ReproTranscript(
        scenario_name="Test Scenario",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
    )
    t.steps.append(ReproStep(
        action="GET /v2/projects/123",
        request_summary="test",
        response_code=code,
        response_summary=response_summary,
        latency_ms=50,
        error=error,
        friction=friction,
    ))
    if friction:
        t.frictions_found.append(friction)
    t.compute_hash()
    return t


def test_transcript_to_golden_captures_contract():
    """Golden snapshots capture response codes and fields, not timing."""
    t = _make_transcript()
    golden = transcript_to_golden(t)
    assert golden["scenario_name"] == "Test Scenario"
    assert golden["step_count"] == 1
    assert golden["steps"][0]["response_code"] == 200
    assert "id" in golden["steps"][0]["response_fields"]
    assert "name" in golden["steps"][0]["response_fields"]
    assert golden["friction_count"] == 0


def test_save_and_load_golden(tmp_path):
    """Golden files round-trip through save/load."""
    t = _make_transcript()
    path = save_golden(t, str(tmp_path))
    loaded = load_golden(path)
    assert loaded is not None
    assert loaded["scenario_name"] == "Test Scenario"
    assert loaded["sha256"] == t.sha256


def test_load_golden_missing_file():
    assert load_golden("/nonexistent/path.json") is None


def test_compare_identical_transcripts():
    """Identical transcripts should pass."""
    t = _make_transcript()
    golden = transcript_to_golden(t)
    result = compare_transcript(t, golden)
    assert result.passed
    assert result.diffs == []
    assert result.transcript_hash_match


def test_compare_detects_response_code_regression():
    """200→500 is a breaking regression."""
    baseline = _make_transcript(code=200)
    golden = transcript_to_golden(baseline)
    actual = _make_transcript(code=500)
    result = compare_transcript(actual, golden)
    assert not result.passed
    assert any(d.field == "response_code" and d.severity == "breaking" for d in result.diffs)


def test_compare_detects_new_friction():
    """New friction where there was none is a regression."""
    baseline = _make_transcript()
    golden = transcript_to_golden(baseline)
    actual = _make_transcript(friction="Slow response: took 5000ms")
    result = compare_transcript(actual, golden)
    assert not result.passed
    assert len(result.new_frictions) == 1


def test_compare_detects_resolved_friction():
    """Friction that disappears is an improvement, not a failure."""
    baseline = _make_transcript(friction="Slow response: took 5000ms")
    golden = transcript_to_golden(baseline)
    actual = _make_transcript()
    result = compare_transcript(actual, golden)
    assert result.passed  # Improvement, not failure
    assert len(result.resolved_frictions) == 1


def test_compare_detects_missing_response_fields():
    """Disappearing response fields is breaking."""
    baseline = _make_transcript(response_summary='{"id": "1", "name": "Test", "apps": []}')
    golden = transcript_to_golden(baseline)
    actual = _make_transcript(response_summary='{"id": "1"}')
    result = compare_transcript(actual, golden)
    assert not result.passed
    assert any(d.field == "response_fields" for d in result.diffs)


def test_compare_detects_new_error():
    """New error where there wasn't one is breaking."""
    baseline = _make_transcript()
    golden = transcript_to_golden(baseline)
    actual = _make_transcript(error="Internal Server Error")
    result = compare_transcript(actual, golden)
    assert not result.passed
    assert any(d.field == "has_error" for d in result.diffs)


def test_golden_suite_creates_baseline(mock_config, tmp_path):
    """First run creates golden files, reports all pass."""
    golden_dir = str(tmp_path / "golden")
    results = run_golden_suite(mock_config, golden_dir)
    assert len(results) == len(REPRO_SCENARIOS)
    assert all(r.passed for r in results)


def test_golden_suite_passes_on_rerun(mock_config, tmp_path):
    """Second run against same API should match golden."""
    golden_dir = str(tmp_path / "golden")
    run_golden_suite(mock_config, golden_dir)  # Create baseline
    results = run_golden_suite(mock_config, golden_dir)  # Rerun
    assert all(r.passed for r in results)


def test_format_golden_report():
    """Report formatting includes all key info."""
    results = [
        GoldenTestResult(
            scenario_name="Test A", passed=True, diffs=[],
            new_frictions=[], resolved_frictions=[], transcript_hash_match=True,
        ),
        GoldenTestResult(
            scenario_name="Test B", passed=False,
            diffs=[GoldenDiff(0, "response_code", 200, 500, "breaking")],
            new_frictions=["Slow response"], resolved_frictions=[],
            transcript_hash_match=False,
        ),
    ]
    md = format_golden_report(results)
    assert "FAIL" in md
    assert "1/2" in md
    assert "Test B" in md
    assert "breaking" in md
