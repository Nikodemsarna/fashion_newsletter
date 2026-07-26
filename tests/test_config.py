import pytest

from fashion_trends.config import Settings


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "ANTHROPIC_API_KEY",
        "FASHION_PROVIDER",
        "FASHION_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_no_keys_means_no_analyzer(monkeypatch):
    s = Settings.from_env()
    assert s.provider == "none"
    assert s.has_analyzer is False


def test_gemini_autodetected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    s = Settings.from_env()
    assert s.provider == "gemini"
    assert s.has_analyzer is True
    assert s.resolved_model == "gemini-flash-latest"
    assert s.api_key == "x"


def test_free_provider_preferred_over_anthropic(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    s = Settings.from_env()
    assert s.provider == "groq"
    assert s.resolved_model == "llama-3.3-70b-versatile"


def test_explicit_provider_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("FASHION_PROVIDER", "anthropic")
    s = Settings.from_env()
    assert s.provider == "anthropic"
    assert s.resolved_model == "claude-opus-4-8"
    assert s.api_key == "a"


def test_model_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("FASHION_MODEL", "gemini-1.5-flash")
    s = Settings.from_env()
    assert s.resolved_model == "gemini-1.5-flash"


def test_google_api_key_alias(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    s = Settings.from_env()
    assert s.provider == "gemini"
    assert s.has_analyzer is True
