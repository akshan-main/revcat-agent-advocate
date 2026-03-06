import pytest
from pydantic import ValidationError

from advocate.config import Config, SafetyError


def test_default_values():
    config = Config(_env_file=None)
    assert config.dry_run is True
    assert config.allow_writes is False
    assert config.demo_mode is False


def test_rc_key_validation_sk():
    config = Config(revenuecat_api_key="sk_test_123", _env_file=None)
    assert config.revenuecat_api_key == "sk_test_123"


def test_rc_key_validation_atk():
    config = Config(revenuecat_api_key="atk_test_123", _env_file=None)
    assert config.revenuecat_api_key == "atk_test_123"


def test_rc_key_validation_invalid():
    with pytest.raises(ValidationError):
        Config(revenuecat_api_key="invalid_key", _env_file=None)


def test_rc_key_none_is_valid():
    config = Config(revenuecat_api_key=None, _env_file=None)
    assert config.revenuecat_api_key is None


def test_has_rc_credentials():
    config = Config(revenuecat_api_key="sk_test", _env_file=None)
    assert config.has_rc_credentials is True

    config2 = Config(_env_file=None)
    assert config2.has_rc_credentials is False


def test_has_anthropic():
    config = Config(anthropic_api_key="sk-ant-test", _env_file=None)
    assert config.has_anthropic is True

    config2 = Config(_env_file=None)
    assert config2.has_anthropic is False


def test_has_github():
    config = Config(github_token="ghp_test", github_repo="user/repo", _env_file=None)
    assert config.has_github is True

    config2 = Config(github_token="ghp_test", _env_file=None)
    assert config2.has_github is False


def test_safety_error():
    err = SafetyError("blocked")
    assert str(err) == "blocked"
