"""Pytest configuration for StoryGraph backend tests."""
import pytest


@pytest.fixture(autouse=True)
def disable_live_llm_during_tests(monkeypatch):
    """Ensure automated tests run deterministically and fast without consuming live LLM quota."""
    monkeypatch.setattr("app.config.GEMINI_API_KEY", "")
    monkeypatch.setattr("app.config.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.llm.interpreter.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.llm.generator.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.config.get_llm_client", lambda: (None, None))
    monkeypatch.setattr("app.llm.interpreter.get_llm_client", lambda: (None, None))
    monkeypatch.setattr("app.llm.generator.get_llm_client", lambda: (None, None))
