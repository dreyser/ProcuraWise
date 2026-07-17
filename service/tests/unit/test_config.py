from procurawise.shared.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "local"
    assert settings.log_level == "info"


def test_settings_reads_env_override(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    assert settings.environment == "test"
