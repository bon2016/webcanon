"""WebCanon: policy-aware web retrieval for AI.

WebCanon turns URLs into trustworthy, policy-checked, citation-ready context
for LLMs. It evaluates ``robots.txt`` (RFC 9309), resolves LLM-friendly
alternatives via ``llms.txt``, discovers URLs via ``sitemap.xml``, fetches
content behind an SSRF guard, converts HTML to Markdown, and returns full
provenance for every retrieved document.

The retrieval *constitution* (see ``docs/``):

1. Search results are leads, not sources.
2. robots.txt is evaluated before fetch.
3. llms.txt can guide retrieval, not override policy.
4. Every transformed document must retain provenance.
5. Web content is untrusted input.
6. Markdown is an interface, not the source of truth.
7. Extraction quality must be measurable.
"""

from .client import WebCanon
from .config import (
    ExtractionConfig,
    LlmsConfig,
    RetrievalConfig,
    RobotsConfig,
    UserAgentConfig,
)
from .errors import (
    PolicyError,
    SsrfError,
    WebCanonError,
)
from .hooks import (
    AiContext,
    AiHint,
    AiResolver,
    Extractor,
    Fetcher,
)
from .ai import AnthropicAiResolver, ai_resolver_from_env
from .headless import PlaywrightFetcher
from .robots import RobotsPolicy, RobotsVerdict, evaluate_robots, parse_robots
from .schema import RETRIEVE_TOOL, as_anthropic_tool, as_openai_tool
from .types import RetrievalResult

__version__ = "0.4.0"

__all__ = [
    "WebCanon",
    "RetrievalConfig",
    "RobotsConfig",
    "LlmsConfig",
    "ExtractionConfig",
    "UserAgentConfig",
    "AiContext",
    "AiHint",
    "AiResolver",
    "Fetcher",
    "Extractor",
    "PlaywrightFetcher",
    "AnthropicAiResolver",
    "ai_resolver_from_env",
    "RetrievalResult",
    "RobotsPolicy",
    "RobotsVerdict",
    "parse_robots",
    "evaluate_robots",
    "RETRIEVE_TOOL",
    "as_openai_tool",
    "as_anthropic_tool",
    "WebCanonError",
    "PolicyError",
    "SsrfError",
    "__version__",
]
