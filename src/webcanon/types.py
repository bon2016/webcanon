"""Result and provenance types returned by WebCanon.

These mirror the ``RetrievalResult`` shape described in the design memo
(section 8). Everything is a plain dataclass so callers can serialise with
:func:`webcanon.types.to_dict`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

SelectedBy = Literal["direct", "llms_txt", "sitemap", "search_result", "canonical"]
FetchRecommendation = Literal[
    "recommended",
    "not_recommended",
    "allowed_but_warn",
    "unknown_do_not_fetch_by_default",
]


@dataclass
class RequestInfo:
    input: str
    mode: Literal["url", "search"]
    timestamp: str


@dataclass
class SelectedSource:
    final_url: str
    selected_by: SelectedBy
    requested_url: Optional[str] = None


@dataclass
class RobotsDecision:
    verdict: str
    user_agent: str
    requested_url: str
    recommendation: FetchRecommendation
    reason: str
    matched_rule: Optional[dict[str, Any]] = None


@dataclass
class LlmsDecision:
    strategy: str
    selected_url: Optional[str] = None
    reason: str = ""
    # "rule_based" (built-in resolver) or "ai" (injected ai_resolver).
    resolved_by: str = "rule_based"
    # Extra request headers an AI resolver asked us to send.
    applied_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class PolicyInfo:
    robots: Optional[RobotsDecision] = None
    llms: Optional[LlmsDecision] = None


@dataclass
class FetchInfo:
    status: int
    content_type: str
    final_url: str
    fetched_at: str
    redirects: list[str] = field(default_factory=list)
    etag: Optional[str] = None
    last_modified: Optional[str] = None


@dataclass
class ExtractionInfo:
    extractor: str
    quality_score: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class Document:
    markdown: str
    text: str
    title: Optional[str] = None
    links: list[str] = field(default_factory=list)


@dataclass
class ManifestRefs:
    sitemap_urls: list[str] = field(default_factory=list)
    robots_url: Optional[str] = None
    llms_url: Optional[str] = None


@dataclass
class Provenance:
    source_hash: str
    markdown_hash: str
    manifests: ManifestRefs = field(default_factory=ManifestRefs)


@dataclass
class RetrievalResult:
    """The full, audit-friendly result of a retrieval.

    This is the Retrieval Bill of Materials: it answers *why* a URL was read,
    whether policy allowed it, whether ``llms.txt`` rerouted it, how good the
    extraction was, and whether the run is reproducible.
    """

    request: RequestInfo
    selected_source: SelectedSource
    policy: PolicyInfo
    fetch: FetchInfo
    extraction: ExtractionInfo
    document: Document
    provenance: Provenance

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_document(self) -> dict[str, Any]:
        """Return a framework-neutral document shape.

        The keys are chosen so adapters for LangChain, LlamaIndex, Haystack,
        etc. can map them with a one-liner. ``content`` is duplicated as both
        ``page_content`` (LangChain) and ``text`` (LlamaIndex) to avoid glue.
        See ``docs/ai-framework-affinity.md`` for the mapping cheat-sheet.
        """

        content = self.document.markdown
        metadata: dict[str, Any] = {
            "source": self.selected_source.final_url,
            "requested_url": self.selected_source.requested_url,
            "selected_by": self.selected_source.selected_by,
            "title": self.document.title,
            "content_type": self.fetch.content_type,
            "source_hash": self.provenance.source_hash,
            "markdown_hash": self.provenance.markdown_hash,
            "quality_score": self.extraction.quality_score,
        }
        if self.policy.robots is not None:
            metadata["robots_verdict"] = self.policy.robots.verdict
            metadata["robots_recommendation"] = self.policy.robots.recommendation
        if self.extraction.warnings:
            metadata["warnings"] = list(self.extraction.warnings)
        return {"content": content, "page_content": content, "text": content,
                "metadata": metadata}

    def to_markdown_with_citation(self) -> str:
        """Render the document as a string with a trailing source citation.

        Useful for tools/agents that only accept a text return value.
        """

        url = self.selected_source.final_url
        raw_title = self.document.title or url
        title = raw_title.replace("\\", "\\\\").replace("]", "\\]").replace("\r", " ").replace("\n", " ")
        return f"{self.document.markdown}\n\n---\nSource: [{title}](<{url}>)"
