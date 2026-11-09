"""Settings: bad values must stop the app at startup with a clear message."""

import pytest

from app.config import load_settings


def test_defaults_load(monkeypatch):
    for name in ("LLM_PROVIDER", "SEARCH_MODE", "ANSWER_EFFORT", "OLLAMA_URL", "COOKIE_SECURE"):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings()
    assert (settings.llm_provider, settings.search_mode, settings.answer_effort) == ("ollama", "hybrid", "low")
    assert settings.ollama_url == "http://localhost:11434"
    assert settings.cookie_secure is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_PROVIDER", "openai"),
        ("LLM_PROVIDER", "Ollama"),  # case matters: no silent guessing
        ("SEARCH_MODE", "keyword"),
        ("ANSWER_EFFORT", "extreme"),
        ("ANSWER_EFFORT", ""),
    ],
)
def test_a_value_outside_the_allowed_set_fails_at_startup(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        load_settings()


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://ollama:11434", "ollama:11434", "", "javascript:alert(1)"])
def test_the_ollama_url_must_be_http(monkeypatch, url):
    monkeypatch.setenv("OLLAMA_URL", url)
    with pytest.raises(ValueError, match="OLLAMA_URL"):
        load_settings()


def test_a_trailing_slash_in_the_ollama_url_is_dropped(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434/")
    assert load_settings().ollama_url == "http://ollama:11434"


@pytest.mark.parametrize(
    ("value", "expected"), [("true", True), ("1", True), ("YES", True), ("false", False), ("no", False)]
)
def test_cookie_secure_reads_common_spellings(monkeypatch, value, expected):
    monkeypatch.setenv("COOKIE_SECURE", value)
    assert load_settings().cookie_secure is expected


@pytest.mark.parametrize("name", ["CHUNK_SIZE", "TOP_K", "MIN_SCORE"])
def test_numbers_must_be_numbers(monkeypatch, name):
    monkeypatch.setenv(name, "five")
    with pytest.raises(ValueError):
        load_settings()
