"""Tests for operational reliability: idempotency, circuit breakers, alerting."""
from advocate.reliability.ops import (
    idempotency_key,
    check_idempotency,
    store_idempotency,
    get_circuit_state,
    record_success,
    record_failure,
    is_service_available,
    log_alert,
    get_recent_alerts,
    format_alert_dashboard,
    retry_with_backoff,
    RetryConfig,
    FAILURE_THRESHOLD,
    init_reliability_db,
)


def test_idempotency_key_deterministic():
    k1 = idempotency_key("write-content", {"topic": "test"})
    k2 = idempotency_key("write-content", {"topic": "test"})
    assert k1 == k2
    assert len(k1) == 32


def test_idempotency_key_different_params():
    k1 = idempotency_key("write-content", {"topic": "a"})
    k2 = idempotency_key("write-content", {"topic": "b"})
    assert k1 != k2


def test_check_store_idempotency(db_conn):
    key = idempotency_key("test-op", {"x": 1})
    assert check_idempotency(db_conn, key) is None

    store_idempotency(db_conn, key, {"result": "ok"})
    cached = check_idempotency(db_conn, key)
    assert cached is not None
    assert cached["result"] == "ok"


def test_idempotency_expiry(db_conn):
    key = idempotency_key("test-expire", {})
    # Store with 0 TTL, should be expired
    store_idempotency(db_conn, key, {"result": "expired"}, ttl_hours=0)
    # Give it a moment to expire
    result = check_idempotency(db_conn, key)
    # TTL=0 means it expires immediately
    assert result is None


def test_circuit_breaker_closed_by_default(db_conn):
    state = get_circuit_state(db_conn, "test-service")
    assert state == "closed"


def test_circuit_breaker_opens_after_threshold(db_conn):
    for _ in range(FAILURE_THRESHOLD):
        record_failure(db_conn, "failing-service")
    state = get_circuit_state(db_conn, "failing-service")
    assert state == "open"
    assert not is_service_available(db_conn, "failing-service")


def test_circuit_breaker_resets_on_success(db_conn):
    record_failure(db_conn, "flaky-service")
    record_failure(db_conn, "flaky-service")
    record_success(db_conn, "flaky-service")
    state = get_circuit_state(db_conn, "flaky-service")
    assert state == "closed"
    assert is_service_available(db_conn, "flaky-service")


def test_alert_logging(db_conn):
    log_alert(db_conn, "error", "test", "Something went wrong", {"detail": "info"})
    log_alert(db_conn, "warning", "test", "Heads up")
    log_alert(db_conn, "info", "test", "All good")

    all_alerts = get_recent_alerts(db_conn)
    assert len(all_alerts) == 3

    errors = get_recent_alerts(db_conn, level="error")
    assert len(errors) == 1
    assert errors[0]["message"] == "Something went wrong"


def test_format_alert_dashboard(db_conn):
    init_reliability_db(db_conn)
    log_alert(db_conn, "error", "api", "API timeout")
    dashboard = format_alert_dashboard(db_conn)
    assert "Operational Dashboard" in dashboard
    assert "API timeout" in dashboard


def test_retry_with_backoff_success():
    call_count = 0

    @retry_with_backoff(config=RetryConfig(max_retries=3, base_delay=0.01))
    def succeeds():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = succeeds()
    assert result == "ok"
    assert call_count == 1


def test_retry_with_backoff_eventual_success():
    call_count = 0

    @retry_with_backoff(config=RetryConfig(max_retries=3, base_delay=0.01, retryable_exceptions=(ValueError,)))
    def fails_then_succeeds():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient")
        return "ok"

    result = fails_then_succeeds()
    assert result == "ok"
    assert call_count == 3


def test_retry_with_backoff_exhausted():
    call_count = 0

    @retry_with_backoff(config=RetryConfig(max_retries=2, base_delay=0.01, retryable_exceptions=(ValueError,)))
    def always_fails():
        nonlocal call_count
        call_count += 1
        raise ValueError("permanent")

    try:
        always_fails()
        assert False, "Should have raised"
    except ValueError:
        assert call_count == 3  # initial + 2 retries
