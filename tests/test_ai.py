"""Tests for the env-configurable AI resolver."""

import sys
import types

import pytest

from webcanon.ai import AnthropicAiResolver, ai_resolver_from_env
from webcanon.hooks import AiContext, AiHint
from webcanon.llms import LlmsLink, LlmsManifest


def _ctx():
    return AiContext(
        requested_url="https://example.com/docs/api",
        origin="https://example.com",
        llms_manifest=LlmsManifest(
            title="Site",
            links=[LlmsLink(title="API", url="https://example.com/docs/api.md")],
        ),
        llms_url="https://example.com/llms.txt",
        robots_recommendation="recommended",
        robots_verdict="allowed_implicit",
    )


# -- env factory --------------------------------------------------------
def test_env_factory_disabled_by_default(monkeypatch):
    monkeypatch.delenv("WEBCANON_AI_PROVIDER", raising=False)
    assert ai_resolver_from_env() is None


def test_env_factory_none_value(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "none")
    assert ai_resolver_from_env() is None


def test_env_factory_anthropic(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("WEBCANON_AI_MODEL", "claude-opus-4-8")
    resolver = ai_resolver_from_env()
    assert isinstance(resolver, AnthropicAiResolver)
    assert resolver.model == "claude-opus-4-8"


def test_env_factory_unknown_provider(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        ai_resolver_from_env()


# -- resolver behaviour -------------------------------------------------
def test_resolver_declines_without_anthropic_installed(monkeypatch):
    # Ensure 'anthropic' import fails inside __call__.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    resolver = AnthropicAiResolver()
    assert resolver(_ctx()) is None


def test_resolver_parses_tool_use_and_sanitizes_headers(monkeypatch):
    # Build a fake 'anthropic' module whose client returns a tool_use block.
    class _Block:
        type = "tool_use"
        input = {
            "url": "https://example.com/docs/api.md",
            "headers": {"Accept": "text/markdown", "Authorization": "Bearer x"},
            "reason": "markdown variant",
        }

    class _Resp:
        content = [_Block()]

    class _Messages:
        def create(self, **kwargs):
            # The tool is forced and the prompt includes the llms link.
            assert kwargs["tool_choice"]["name"] == "choose_fetch_target"
            assert "example.com/docs/api.md" in kwargs["messages"][0]["content"]
            return _Resp()

    class _Client:
        def __init__(self, *a, **k):
            self.messages = _Messages()

    fake = types.SimpleNamespace(Anthropic=_Client)
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    hint = AnthropicAiResolver()(_ctx())
    assert isinstance(hint, AiHint)
    assert hint.url == "https://example.com/docs/api.md"
    # Authorization is dropped; Accept survives.
    assert hint.headers == {"Accept": "text/markdown"}
    assert hint.extra["model"] == "claude-opus-4-8"


def test_resolver_declines_on_api_error(monkeypatch):
    class _Messages:
        def create(self, **kwargs):
            raise RuntimeError("boom")

    class _Client:
        def __init__(self, *a, **k):
            self.messages = _Messages()

    fake = types.SimpleNamespace(Anthropic=_Client)
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    assert AnthropicAiResolver()(_ctx()) is None
