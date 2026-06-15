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
