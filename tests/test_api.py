import pytest
import responses

from advocate.config import Config, SafetyError
from advocate.revenuecat.api import RevenueCatClient, RevenueCatAPIError


def _make_client(allow_writes=False):
    config = Config(
        revenuecat_api_key="sk_test_123",
        revenuecat_project_id="proj_test",
        allow_writes=allow_writes,
        _env_file=None,
    )
    return RevenueCatClient(config)


def test_safety_gate_blocks_post():
    client = _make_client(allow_writes=False)
    with pytest.raises(SafetyError, match="Write operation blocked"):
        client._request("POST", "/projects/proj_test/offerings")


def test_safety_gate_allows_get():
    client = _make_client(allow_writes=False)
    # GET should not raise SafetyError (it will fail with ConnectionError though)
    # We just check it doesn't raise SafetyError
    try:
        client._request("GET", "/projects/proj_test")
    except SafetyError:
        pytest.fail("GET should not be blocked by safety gate")
    except Exception:
        pass  # Expected, no real server


def test_safety_gate_allows_post_when_enabled():
    client = _make_client(allow_writes=True)
    # POST should not raise SafetyError
    try:
        client._request("POST", "/projects/proj_test/offerings")
    except SafetyError:
        pytest.fail("POST should be allowed when allow_writes=True")
    except Exception:
        pass  # Expected, no real server


@responses.activate
def test_get_project():
    responses.add(
        responses.GET,
        "https://api.revenuecat.com/v2/projects/proj_test",
        json={"id": "proj_test", "name": "Test Project"},
        status=200,
    )
    client = _make_client()
    result = client.get_project()
    assert result["id"] == "proj_test"


@responses.activate
def test_list_apps():
    responses.add(
        responses.GET,
        "https://api.revenuecat.com/v2/projects/proj_test/apps",
        json={"items": [{"id": "app_1"}]},
        status=200,
    )
    client = _make_client()
    result = client.list_apps()
    assert len(result["items"]) == 1


@responses.activate
def test_429_retry():
    # First call returns 429, second returns 200
    responses.add(
        responses.GET,
        "https://api.revenuecat.com/v2/projects/proj_test",
        status=429,
        headers={"Retry-After": "0"},
    )
    responses.add(
        responses.GET,
        "https://api.revenuecat.com/v2/projects/proj_test",
        json={"id": "proj_test"},
        status=200,
    )
    client = _make_client()
    result = client.get_project()
    assert result["id"] == "proj_test"


@responses.activate
def test_api_error():
    responses.add(
        responses.GET,
        "https://api.revenuecat.com/v2/projects/proj_test",
        json={"error": "not found"},
        status=404,
    )
    client = _make_client()
    with pytest.raises(RevenueCatAPIError) as exc_info:
        client.get_project()
    assert exc_info.value.status_code == 404
