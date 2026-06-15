"""Configuration objects for WebCanon retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from .hooks import AiResolver, Extractor, Fetcher

RobotsMode = Literal["respect", "report_only", "ignore"]
OnUnavailable = Literal["allow_with_warning", "deny"]
OnUnreachable = Literal["allow_with_warning", "deny"]
LlmsStrategy = Literal["disabled", "prefer", "force"]
ExtractionFormat = Literal["markdown", "text"]


@dataclass(frozen=True)
class UserAgentConfig:
    """Identity advertised to origins and matched against ``robots.txt``.

    ``product`` is the token matched (case-insensitively) against
    ``User-agent`` groups in ``robots.txt``.
    """

    product: str = "WebCanon"
    version: str = "0.1.0"
    contact: str | None = None

    @property
    def header(self) -> str:
        parts = [f"{self.product}/{self.version}"]
        if self.contact:
            parts.append(f"(+{self.contact})")
        return " ".join(parts)


@dataclass(frozen=True)
class RobotsConfig:
    """How ``robots.txt`` results influence retrieval.

    - ``respect``: a ``disallowed`` verdict raises :class:`PolicyError`.
    - ``report_only``: the verdict is recorded but never blocks fetching.
    - ``ignore``: ``robots.txt`` is not even fetched.
    """

    mode: RobotsMode = "respect"
    on_unavailable: OnUnavailable = "allow_with_warning"
    on_unreachable: OnUnreachable = "deny"
    # Per RFC 9309, robots.txt caching should not exceed 24h by default.
    max_cache_seconds: int = 24 * 60 * 60


@dataclass(frozen=True)
class LlmsConfig:
    """How ``llms.txt`` is used to resolve LLM-friendly alternatives."""

    strategy: LlmsStrategy = "prefer"


@dataclass(frozen=True)
class ExtractionConfig:
    """HTML-to-Markdown extraction settings."""

    format: ExtractionFormat = "markdown"


@dataclass(frozen=True)
class FetchConfig:
    """HTTP transport limits. These also bound SSRF blast radius."""

    timeout_seconds: float = 20.0
    max_redirects: int = 5
    max_body_bytes: int = 8 * 1024 * 1024
    allowed_content_types: tuple[str, ...] = (
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/xml",
        "text/xml",
    )
    # Disable to allow loopback/private targets (e.g. tests against localhost).
    block_private_addresses: bool = True


@dataclass(frozen=True)
class RetrievalConfig:
    """Top-level configuration for a :class:`WebCanon` client."""

    user_agent: UserAgentConfig = field(default_factory=UserAgentConfig)
    robots: RobotsConfig = field(default_factory=RobotsConfig)
    llms: LlmsConfig = field(default_factory=LlmsConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)

    # -- customization hooks (None => built-in default) -----------------
    # Swap the scraping transport, the HTML->Markdown converter, and the AI
    # that reasons over llms.txt + URL. See webcanon.hooks.
    fetcher: "Optional[Fetcher]" = None
    extractor: "Optional[Extractor]" = None
    ai_resolver: "Optional[AiResolver]" = None
