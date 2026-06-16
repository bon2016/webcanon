"""Tests for the env-configurable AI resolver."""

import sys
import types

import pytest

from webcanon.ai import (
    DEFAULT_MODELS,
    SUPPORTED_PROVIDERS,
    AnthropicAiResolver,
    GeminiAiResolver,
    OpenAiAiResolver,
    ai_resolver_from_env,
    build_ai_resolver,
)
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


def test_env_factory_openai_default_model(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "openai")
    monkeypatch.delenv("WEBCANON_AI_MODEL", raising=False)
    resolver = ai_resolver_from_env()
    assert isinstance(resolver, OpenAiAiResolver)
    assert resolver.model == DEFAULT_MODELS["openai"]


def test_env_factory_gemini_default_model(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "gemini")
    monkeypatch.delenv("WEBCANON_AI_MODEL", raising=False)
    resolver = ai_resolver_from_env()
    assert isinstance(resolver, GeminiAiResolver)
    assert resolver.model == DEFAULT_MODELS["gemini"]


def test_env_factory_model_override_applies_to_each_provider(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "openai")
    monkeypatch.setenv("WEBCANON_AI_MODEL", "gpt-4o-mini")
    assert ai_resolver_from_env().model == "gpt-4o-mini"


def test_env_factory_unknown_provider(monkeypatch):
    monkeypatch.setenv("WEBCANON_AI_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        ai_resolver_from_env()


# -- build_ai_resolver (explicit provider/model) ------------------------
def test_build_disabled_values():
    assert build_ai_resolver("") is None
    assert build_ai_resolver("none") is None
    assert build_ai_resolver("disabled") is None


def test_build_each_provider_default_model():
    assert isinstance(build_ai_resolver("anthropic"), AnthropicAiResolver)
    assert build_ai_resolver("openai").model == DEFAULT_MODELS["openai"]
    assert build_ai_resolver("gemini").model == DEFAULT_MODELS["gemini"]


def test_build_model_override():
    r = build_ai_resolver("openai", "gpt-4o")
    assert isinstance(r, OpenAiAiResolver)
    assert r.model == "gpt-4o"


def test_build_unknown_provider():
    with pytest.raises(ValueError):
        build_ai_resolver("bogus")


def test_supported_providers_constant():
    assert set(SUPPORTED_PROVIDERS) == {"anthropic", "openai", "gemini"}


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


# -- OpenAI -------------------------------------------------------------
def _install_fake_openai(monkeypatch, *, arguments=None, raise_error=False):
    import json as _json

    _payload = _json.dumps(
        arguments
        if arguments is not None
        else {
            "url": "https://example.com/docs/api.md",
            "headers": {"Accept": "text/markdown", "Cookie": "x=1"},
            "reason": "markdown variant",
        }
    )

    class _Fn:
        name = "choose_fetch_target"
        arguments = _payload

    class _Call:
        function = _Fn()

    class _Msg:
        tool_calls = [_Call()]

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            if raise_error:
                raise RuntimeError("boom")
            assert kwargs["tool_choice"]["function"]["name"] == "choose_fetch_target"
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_Client))


def test_openai_declines_without_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)
    assert OpenAiAiResolver()(_ctx()) is None


def test_openai_parses_function_call_and_sanitizes_headers(monkeypatch):
    _install_fake_openai(monkeypatch)
    hint = OpenAiAiResolver(model="gpt-5")(_ctx())
    assert isinstance(hint, AiHint)
    assert hint.url == "https://example.com/docs/api.md"
    assert hint.headers == {"Accept": "text/markdown"}  # Cookie dropped
    assert hint.extra == {"model": "gpt-5", "provider": "openai"}


def test_openai_declines_on_api_error(monkeypatch):
    _install_fake_openai(monkeypatch, raise_error=True)
    assert OpenAiAiResolver()(_ctx()) is None


# -- Gemini -------------------------------------------------------------
def _install_fake_gemini(monkeypatch, *, args=None, raise_error=False):
    _call_args = (
        args
        if args is not None
        else {
            "url": "https://example.com/docs/api.md",
            "headers": {"Accept": "text/markdown", "Authorization": "Bearer y"},
            "reason": "markdown variant",
        }
    )

    class _Call:
        name = "choose_fetch_target"
        args = _call_args

    class _Resp:
        function_calls = [_Call()]

    class _Models:
        def generate_content(self, **kwargs):
            if raise_error:
                raise RuntimeError("boom")
            return _Resp()

    class _Client:
        def __init__(self, *a, **k):
            self.models = _Models()

    genai = types.SimpleNamespace(Client=_Client)
    # Minimal stand-ins for google.genai.types factory calls.
    types_mod = types.SimpleNamespace(
        FunctionDeclaration=lambda **k: ("fn", k),
        Tool=lambda **k: ("tool", k),
        ToolConfig=lambda **k: ("toolcfg", k),
        FunctionCallingConfig=lambda **k: ("fcc", k),
        GenerateContentConfig=lambda **k: ("cfg", k),
    )
    google_pkg = types.ModuleType("google")
    genai_pkg = types.ModuleType("google.genai")
    genai_pkg.Client = _Client
    types_submod = types.ModuleType("google.genai.types")
    for name, fn in vars(types_mod).items():
        setattr(types_submod, name, fn)
    google_pkg.genai = genai_pkg
    genai_pkg.types = types_submod
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.genai", genai_pkg)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_submod)


def test_gemini_declines_without_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "google.genai", None)
    assert GeminiAiResolver()(_ctx()) is None


def test_gemini_parses_function_call_and_sanitizes_headers(monkeypatch):
    _install_fake_gemini(monkeypatch)
    hint = GeminiAiResolver(model="gemini-2.5-pro", api_key="k")(_ctx())
    assert isinstance(hint, AiHint)
    assert hint.url == "https://example.com/docs/api.md"
    assert hint.headers == {"Accept": "text/markdown"}  # Authorization dropped
    assert hint.extra == {"model": "gemini-2.5-pro", "provider": "gemini"}


def test_gemini_declines_on_api_error(monkeypatch):
    _install_fake_gemini(monkeypatch, raise_error=True)
    assert GeminiAiResolver(api_key="k")(_ctx()) is None
