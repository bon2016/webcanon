"""Customization hooks: pluggable fetch, extraction, and AI resolution.

WebCanon's pipeline runs through three replaceable callables so callers can
swap in their own scraping transport, their own HTML->Markdown converter, and
(most importantly) their own AI to reason over ``llms.txt`` and the target URL.

All three default to the built-in implementations; pass alternatives via
:class:`webcanon.config.RetrievalConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Protocol

if TYPE_CHECKING:  # avoid import cycles at runtime
    from .config import FetchConfig, UserAgentConfig
    from .extract import ExtractedDocument
    from .fetch import FetchResponse
    from .llms import LlmsManifest


class Fetcher(Protocol):
    """A scraping transport.

    Implementations must honour the SSRF guard for any URL they request. The
    built-in :func:`webcanon.fetch.fetch` already does. ``headers`` carries any
    extra request headers requested by an AI resolver (see :class:`AiHint`).
    """

    def __call__(
        self,
        url: str,
        *,
        config: "FetchConfig",
        user_agent: "UserAgentConfig",
        headers: Optional[dict[str, str]] = None,
    ) -> "FetchResponse": ...


class Extractor(Protocol):
    """An HTML/content -> Markdown converter."""

    def __call__(
        self, body: str, *, content_type: str
    ) -> "ExtractedDocument": ...


@dataclass
class AiContext:
    """Everything handed to an AI resolver so it can reason about a fetch.

    This is the realisation of "pass ``llms.txt`` and the URL to the AI": the
    requested URL, the parsed ``llms.txt`` manifest (may be ``None``), and the
    robots recommendation already computed for the requested URL.
    """

    requested_url: str
    origin: str
    llms_manifest: Optional["LlmsManifest"]
    llms_url: Optional[str]
    robots_recommendation: str
    robots_verdict: str


@dataclass
class AiHint:
    """An AI resolver's recommendation for how to scrape.

    - ``url``: the URL to actually fetch (may be a ``.md`` variant or an
      ``llms.txt``-listed document; ``None`` keeps the requested URL).
    - ``headers``: extra request headers to send (e.g. an ``Accept`` header
      preferring Markdown, per the requirement that some docs want a specific
      header).
    - ``reason``: human-readable explanation, recorded in provenance.
    """

    url: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class AiResolver(Protocol):
    """A callable that reasons over ``llms.txt`` + URL and returns an AiHint.

    Returning ``None`` means "no opinion; proceed normally".
    """

    def __call__(self, context: AiContext) -> Optional[AiHint]: ...
