"""Built-in AI resolvers, configurable via environment variables.

This turns the abstract ``ai_resolver`` hook (``webcanon.hooks``) into
ready-to-use implementations backed by an LLM. A resolver receives the URL +
parsed ``llms.txt`` + robots verdict and asks the model which URL to fetch and
which (safe) request headers to send.

Three providers are supported — Anthropic (Claude), OpenAI, and Google Gemini —
each behind an optional dependency. Activate one from the environment so the CLI
and library share a single switch::

    export WEBCANON_AI_PROVIDER=anthropic       # or: openai | gemini
    export WEBCANON_AI_MODEL=claude-opus-4-8    # optional (per-provider default)
    # plus the provider's API key:
    #   anthropic -> ANTHROPIC_API_KEY
    #   openai    -> OPENAI_API_KEY
    #   gemini    -> GEMINI_API_KEY (or GOOGLE_API_KEY)

Then::

    from webcanon import WebCanon
    from webcanon.ai import ai_resolver_from_env
    from webcanon.config import RetrievalConfig

    client = WebCanon(RetrievalConfig(ai_resolver=ai_resolver_from_env()))
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)

Install the matching extra: ``pip install "webcanon[ai]"`` (Anthropic),
``"webcanon[openai]"``, or ``"webcanon[gemini]"``. The model is never trusted to
override policy — its choice is re-checked against ``robots.txt`` and the SSRF
guard by the pipeline (see ``docs/security.md``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from .fetch import SAFE_INJECTABLE_HEADERS
from .hooks import AiContext, AiHint

# Per-provider default model.
DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-5",
    "gemini": "gemini-2.5-pro",
}
DEFAULT_MODEL = DEFAULT_MODELS["anthropic"]  # back-compat alias

_TOOL_NAME = "choose_fetch_target"

_SYSTEM_PROMPT = (
    "You help a policy-aware web retriever choose the best URL to fetch for an "
    "LLM. You are given a requested URL, the site's llms.txt (if any), and the "
    "robots.txt verdict. Decide whether to read a different, more "
    "LLM-friendly URL (e.g. a Markdown variant or a doc listed in llms.txt) "
    "and whether to send a content-negotiation header such as "
    "'Accept: text/markdown'. You cannot override robots.txt; the caller "
    "re-checks your choice. Respond with the tool/function call only."
)

# JSON Schema for the tool/function arguments — shared across providers.
_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": (
                "Absolute URL to fetch. Use the requested URL unchanged if no "
                "better option exists."
            ),
        },
        "headers": {
            "type": "object",
            "description": (
                "Optional content-negotiation headers, e.g. "
                '{"Accept": "text/markdown"}. Only Accept, Accept-Language, '
                "Accept-Encoding, If-None-Match, If-Modified-Since are honoured."
            ),
            "additionalProperties": {"type": "string"},
        },
        "reason": {
            "type": "string",
            "description": "One short sentence explaining the choice.",
        },
    },
    "required": ["url", "reason"],
    "additionalProperties": False,
}


def _context_to_prompt(ctx: AiContext) -> str:
    links = []
    if ctx.llms_manifest is not None:
        for link in ctx.llms_manifest.links[:50]:
            section = f" [{link.section}]" if link.section else ""
            links.append(f"- {link.title}{section}: {link.url}")
    llms_block = "\n".join(links) if links else "(no llms.txt or no links)"
    return (
        f"Requested URL: {ctx.requested_url}\n"
        f"Origin: {ctx.origin}\n"
        f"robots verdict: {ctx.robots_verdict} "
        f"(recommendation: {ctx.robots_recommendation})\n"
        f"llms.txt links:\n{llms_block}\n"
    )


def _hint_from_args(data: dict[str, Any], model: str, provider: str) -> AiHint:
    """Build a sanitized :class:`AiHint` from a model's parsed tool arguments."""

    url = data.get("url") or None
    raw_headers = data.get("headers") or {}
    headers = {
        k: v
        for k, v in raw_headers.items()
        if isinstance(v, str) and k.lower() in SAFE_INJECTABLE_HEADERS
    }
    return AiHint(
        url=url if isinstance(url, str) else None,
        headers=headers,
        reason=str(data.get("reason") or f"{provider} ai_resolver"),
        extra={"model": model, "provider": provider},
    )


# -- Anthropic ----------------------------------------------------------
@dataclass
class AnthropicAiResolver:
    """An ``ai_resolver`` backed by Claude via the official ``anthropic`` SDK."""

    model: str = DEFAULT_MODELS["anthropic"]
    api_key: Optional[str] = None
    max_tokens: int = 1024

    def __call__(self, context: AiContext) -> Optional[AiHint]:
        try:
            import anthropic
        except ImportError:
            return None

        client = (
            anthropic.Anthropic(api_key=self.api_key)
            if self.api_key
            else anthropic.Anthropic()
        )
        tool = {
            "name": _TOOL_NAME,
            "description": "Choose the URL to fetch and any safe request headers.",
            "input_schema": _PARAMETERS,
        }
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM_PROMPT,
                tools=[tool],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": _context_to_prompt(context)}],
            )
        except Exception:
            return None

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                data = block.input if isinstance(block.input, dict) else {}
                return _hint_from_args(data, self.model, "anthropic")
        return None


# -- OpenAI -------------------------------------------------------------
@dataclass
class OpenAiAiResolver:
    """An ``ai_resolver`` backed by OpenAI via the official ``openai`` SDK.

    Uses Chat Completions function calling. ``api_key`` overrides
    ``OPENAI_API_KEY``; ``base_url`` overrides ``OPENAI_BASE_URL`` (for
    OpenAI-compatible endpoints).
    """

    model: str = DEFAULT_MODELS["openai"]
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def __call__(self, context: AiContext) -> Optional[AiHint]:
        try:
            import json

            from openai import OpenAI
        except ImportError:
            return None

        kwargs: dict[str, Any] = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        client = OpenAI(**kwargs)

        tools = [
            {
                "type": "function",
                "function": {
                    "name": _TOOL_NAME,
                    "description": (
                        "Choose the URL to fetch and any safe request headers."
                    ),
                    "parameters": _PARAMETERS,
                },
            }
        ]
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _context_to_prompt(context)},
                ],
                tools=tools,
                tool_choice={"type": "function", "function": {"name": _TOOL_NAME}},
            )
        except Exception:
            return None

        try:
            tool_calls = response.choices[0].message.tool_calls or []
        except (AttributeError, IndexError):
            return None
        for call in tool_calls:
            if getattr(call.function, "name", None) == _TOOL_NAME:
                try:
                    data = json.loads(call.function.arguments)
                except (ValueError, TypeError):
                    return None
                if isinstance(data, dict):
                    return _hint_from_args(data, self.model, "openai")
        return None


# -- Gemini -------------------------------------------------------------
@dataclass
class GeminiAiResolver:
    """An ``ai_resolver`` backed by Google Gemini via the ``google-genai`` SDK.

    ``api_key`` overrides ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``.
    """

    model: str = DEFAULT_MODELS["gemini"]
    api_key: Optional[str] = None

    def __call__(self, context: AiContext) -> Optional[AiHint]:
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            return None

        api_key = self.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get(
            "GOOGLE_API_KEY"
        )
        try:
            client = genai.Client(api_key=api_key) if api_key else genai.Client()
        except Exception:
            return None

        function = genai_types.FunctionDeclaration(
            name=_TOOL_NAME,
            description="Choose the URL to fetch and any safe request headers.",
            parameters=_PARAMETERS,
        )
        config = genai_types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            tools=[genai_types.Tool(function_declarations=[function])],
            tool_config=genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(
                    mode="ANY", allowed_function_names=[_TOOL_NAME]
                )
            ),
        )
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=_context_to_prompt(context),
                config=config,
            )
        except Exception:
            return None

        for call in getattr(response, "function_calls", None) or []:
            if getattr(call, "name", None) == _TOOL_NAME:
                data = call.args if isinstance(call.args, dict) else dict(call.args or {})
                return _hint_from_args(data, self.model, "gemini")
        return None


_RESOLVERS = {
    "anthropic": AnthropicAiResolver,
    "openai": OpenAiAiResolver,
    "gemini": GeminiAiResolver,
}


# Providers that can be named on the CLI / in WEBCANON_AI_PROVIDER.
SUPPORTED_PROVIDERS = tuple(_RESOLVERS)


def build_ai_resolver(
    provider: str, model: Optional[str] = None
) -> Optional[object]:
    """Construct an AI resolver by provider name (and optional model).

    ``provider`` is one of :data:`SUPPORTED_PROVIDERS`, or ``""`` / ``none`` /
    ``disabled`` to return ``None``. ``model`` defaults to the provider's entry
    in :data:`DEFAULT_MODELS`. Raises :class:`ValueError` for an unknown
    provider.
    """

    provider = (provider or "").strip().lower()
    if provider in ("", "none", "disabled"):
        return None
    resolver_cls = _RESOLVERS.get(provider)
    if resolver_cls is None:
        supported = ", ".join(repr(p) for p in _RESOLVERS)
        raise ValueError(
            f"unknown AI provider: {provider!r} (supported: {supported})"
        )
    chosen = (model or "").strip() or DEFAULT_MODELS[provider]
    return resolver_cls(model=chosen)


def ai_resolver_from_env() -> Optional[object]:
    """Build an AI resolver from environment variables, or ``None``.

    Reads:

    - ``WEBCANON_AI_PROVIDER`` — ``anthropic`` | ``openai`` | ``gemini`` to
      enable; ``none`` / unset to disable.
    - ``WEBCANON_AI_MODEL`` — model id (per-provider default if unset).
    - provider API key: ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` /
      ``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``).

    Returns ``None`` when no provider is configured, so callers can do
    ``RetrievalConfig(ai_resolver=ai_resolver_from_env())`` unconditionally.
    """

    return build_ai_resolver(
        os.environ.get("WEBCANON_AI_PROVIDER", ""),
        os.environ.get("WEBCANON_AI_MODEL"),
    )
