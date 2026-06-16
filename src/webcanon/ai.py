"""Built-in AI resolvers, configurable via environment variables.

This turns the abstract ``ai_resolver`` hook (``webcanon.hooks``) into a
ready-to-use implementation backed by Claude. The resolver receives the URL +
parsed ``llms.txt`` + robots verdict and asks the model which URL to fetch and
which (safe) request headers to send.

Activate it from the environment so the CLI and library share one switch::

    export WEBCANON_AI_PROVIDER=anthropic       # enable the AI resolver
    export ANTHROPIC_API_KEY=sk-ant-...         # required for the anthropic provider
    export WEBCANON_AI_MODEL=claude-opus-4-8    # optional (this is the default)

Then::

    from webcanon import WebCanon
    from webcanon.ai import ai_resolver_from_env
    from webcanon.config import RetrievalConfig

    client = WebCanon(RetrievalConfig(ai_resolver=ai_resolver_from_env()))
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)

``anthropic`` is an optional dependency: ``pip install "webcanon[ai]"``.
The model is never trusted to override policy — its choice is re-checked against
``robots.txt`` and the SSRF guard by the pipeline (see ``docs/security.md``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from .fetch import SAFE_INJECTABLE_HEADERS
from .hooks import AiContext, AiHint

DEFAULT_MODEL = "claude-opus-4-8"

# The model may only request these; anything else the fetch layer drops anyway.
_SAFE_HEADERS = SAFE_INJECTABLE_HEADERS

_SYSTEM_PROMPT = (
    "You help a policy-aware web retriever choose the best URL to fetch for an "
    "LLM. You are given a requested URL, the site's llms.txt (if any), and the "
    "robots.txt verdict. Decide whether to read a different, more "
    "LLM-friendly URL (e.g. a Markdown variant or a doc listed in llms.txt) "
    "and whether to send a content-negotiation header such as "
    "'Accept: text/markdown'. You cannot override robots.txt; the caller "
    "re-checks your choice. Respond with the tool call only."
)

_TOOL = {
    "name": "choose_fetch_target",
    "description": (
        "Choose the URL to fetch and any safe request headers for an "
        "LLM-friendly retrieval."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": (
                    "Absolute URL to fetch. Use the requested URL unchanged if "
                    "no better option exists."
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
    },
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


@dataclass
class AnthropicAiResolver:
    """An ``ai_resolver`` backed by Claude via the official ``anthropic`` SDK.

    Parameters
    ----------
    model:
        Claude model id (default ``claude-opus-4-8``).
    api_key:
        Overrides ``ANTHROPIC_API_KEY`` if given.
    max_tokens:
        Response cap for the (small) tool call.
    """

    model: str = DEFAULT_MODEL
    api_key: Optional[str] = None
    max_tokens: int = 1024

    def __call__(self, context: AiContext) -> Optional[AiHint]:
        try:
            import anthropic
        except ImportError:
            # AI is opt-in; without the SDK we silently decline (fall back to
            # the rule-based resolver) rather than breaking retrieval.
            return None

        client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else anthropic.Anthropic()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM_PROMPT,
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "choose_fetch_target"},
                messages=[{"role": "user", "content": _context_to_prompt(context)}],
            )
        except Exception:
            # Any API error → decline, let rule-based resolution proceed.
            return None

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                data = block.input if isinstance(block.input, dict) else {}
                url = data.get("url") or None
                raw_headers = data.get("headers") or {}
                headers = {
                    k: v
                    for k, v in raw_headers.items()
                    if isinstance(v, str) and k.lower() in _SAFE_HEADERS
                }
                return AiHint(
                    url=url,
                    headers=headers,
                    reason=data.get("reason", "anthropic ai_resolver"),
                    extra={"model": self.model},
                )
        return None


def ai_resolver_from_env() -> Optional[object]:
    """Build an AI resolver from environment variables, or ``None``.

    Reads:

    - ``WEBCANON_AI_PROVIDER`` — ``anthropic`` to enable; ``none``/unset to disable.
    - ``WEBCANON_AI_MODEL`` — model id (default ``claude-opus-4-8``).
    - ``ANTHROPIC_API_KEY`` — used by the anthropic provider.

    Returns ``None`` when no provider is configured, so callers can do
    ``RetrievalConfig(ai_resolver=ai_resolver_from_env())`` unconditionally.
    """

    provider = os.environ.get("WEBCANON_AI_PROVIDER", "").strip().lower()
    if provider in ("", "none", "disabled"):
        return None
    if provider == "anthropic":
        model = os.environ.get("WEBCANON_AI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        return AnthropicAiResolver(model=model)
    raise ValueError(
        f"unknown WEBCANON_AI_PROVIDER: {provider!r} (supported: 'anthropic')"
    )
