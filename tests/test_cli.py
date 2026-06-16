"""CLI argument handling for AI provider/model selection."""

import argparse

import pytest

from webcanon import cli
from webcanon.ai import AnthropicAiResolver, GeminiAiResolver, OpenAiAiResolver


def _args(**kw):
    base = dict(ai=False, ai_provider=None, ai_model=None)
    base.update(kw)
    return argparse.Namespace(**base)


# -- _ai_enabled --------------------------------------------------------
def test_ai_disabled_by_default():
    assert cli._ai_enabled(_args()) is False
    assert cli._build_ai_resolver(_args()) is None


def test_ai_flag_enables():
    assert cli._ai_enabled(_args(ai=True)) is True


def test_ai_provider_flag_implies_enabled():
    assert cli._ai_enabled(_args(ai_provider="openai")) is True


# -- precedence: flags > env > default ----------------------------------
def test_flag_provider_and_model_win(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("WEBCANON_AI_MODEL", "claude-opus-4-8")
    r = cli._build_ai_resolver(_args(ai_provider="openai", ai_model="gpt-4o"))
    assert isinstance(r, OpenAiAiResolver)
    assert r.model == "gpt-4o"


def test_env_used_when_only_ai_flag(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "gemini")
    monkeypatch.delenv("WEBCANON_AI_MODEL", raising=False)
    r = cli._build_ai_resolver(_args(ai=True))
    assert isinstance(r, GeminiAiResolver)


def test_flag_provider_with_env_model(monkeypatch):
    # provider from flag, model falls back to env
    monkeypatch.delenv("WEBCANON_AI_PROVIDER", raising=False)
    monkeypatch.setenv("WEBCANON_AI_MODEL", "claude-3-5-haiku")
    r = cli._build_ai_resolver(_args(ai_provider="anthropic"))
    assert isinstance(r, AnthropicAiResolver)
    assert r.model == "claude-3-5-haiku"


def test_ai_flag_with_no_env_provider_returns_none(monkeypatch):
    # --ai but nothing configured → no resolver (rule engine is used downstream)
    monkeypatch.delenv("WEBCANON_AI_PROVIDER", raising=False)
    monkeypatch.delenv("WEBCANON_AI_MODEL", raising=False)
    assert cli._build_ai_resolver(_args(ai=True)) is None


def test_unknown_flag_provider_rejected_by_parser():
    # argparse choices reject an unknown provider before our code runs.
    with pytest.raises(SystemExit):
        cli.main(["fetch", "https://example.com", "--ai-provider", "bogus"])
