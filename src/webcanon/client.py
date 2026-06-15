"""WebCanon client: the retrieval pipeline.

Implements the v0.1 flow from the memo (section 10):

    Input URL
      -> origin manifests (robots/llms/sitemap)
      -> robots evaluation of the input URL
      -> (aiReasoning) llms.txt candidate resolution + per-candidate robots
      -> SSRF-guarded fetch
      -> HTML -> Markdown extraction
      -> provenance-bearing RetrievalResult
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from .config import RetrievalConfig
from .errors import FetchError, PolicyError, WebCanonError
from .extract import extract_html
from .fetch import FetchResponse, fetch
from .hooks import AiContext, AiResolver, Extractor, Fetcher
from .llms import LlmsManifest, parse_llms, resolve_candidates
from .provenance import sha256_hex
from .robots import RobotsPolicy, RobotsVerdict, evaluate_robots, parse_robots
from .types import (
    Document,
    ExtractionInfo,
    FetchInfo,
    LlmsDecision,
    ManifestRefs,
    PolicyInfo,
    Provenance,
    RequestInfo,
    RetrievalResult,
    RobotsDecision,
    SelectedSource,
)
from .urls import manifest_url, normalize_url, origin_of

_RECOMMENDATION_BY_VERDICT = {
    RobotsVerdict.ALLOWED_EXPLICIT: "recommended",
    RobotsVerdict.ALLOWED_IMPLICIT: "recommended",
    RobotsVerdict.DISALLOWED_EXPLICIT: "not_recommended",
    RobotsVerdict.UNKNOWN_UNREACHABLE: "unknown_do_not_fetch_by_default",
    RobotsVerdict.UNKNOWN_PARSE_ERROR: "allowed_but_warn",
    RobotsVerdict.SKIPPED_BY_USER_POLICY: "recommended",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WebCanon:
    """Policy-aware retrieval client."""

    def __init__(
        self,
        config: Optional[RetrievalConfig] = None,
        *,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.config = config or RetrievalConfig()
        self._client = client
        # Resolve customization hooks (fall back to built-ins).
        self._fetcher: Fetcher = self.config.fetcher or self._default_fetcher
        self._extractor: Extractor = self.config.extractor or extract_html
        self._ai_resolver: Optional[AiResolver] = self.config.ai_resolver

    # -- default hooks ---------------------------------------------------
    def _default_fetcher(
        self,
        url: str,
        *,
        config,
        user_agent,
        headers: Optional[dict[str, str]] = None,
    ) -> FetchResponse:
        return fetch(
            url,
            config=config,
            user_agent=user_agent,
            client=self._client,
            headers=headers,
        )

    def _do_fetch(
        self, url: str, *, headers: Optional[dict[str, str]] = None
    ) -> FetchResponse:
        return self._fetcher(
            url,
            config=self.config.fetch,
            user_agent=self.config.user_agent,
            headers=headers,
        )

    # -- manifest fetching ----------------------------------------------
    def _fetch_text(self, url: str) -> Optional[FetchResponse]:
        try:
            return self._do_fetch(url)
        except WebCanonError:
            return None

    def _load_robots(self, origin: str) -> tuple[RobotsPolicy, Optional[str], RobotsVerdict]:
        """Return (policy, robots_url, transport_verdict).

        ``transport_verdict`` is non-None only when the transport itself
        decides the outcome (4xx => available/allow, 5xx/unreachable => deny).
        """

        url = manifest_url(origin, "robots.txt")
        resp = self._fetch_text(url)
        if resp is None:
            # Unreachable. Per config, deny or warn.
            verdict = (
                RobotsVerdict.UNKNOWN_UNREACHABLE
                if self.config.robots.on_unreachable == "deny"
                else RobotsVerdict.ALLOWED_IMPLICIT
            )
            return RobotsPolicy(), url, verdict
        if resp.status >= 500:
            return RobotsPolicy(), url, RobotsVerdict.UNKNOWN_UNREACHABLE
        if resp.status >= 400:
            # 4xx => robots unavailable => fetching is allowed (RFC 9309).
            return RobotsPolicy(), url, RobotsVerdict.ALLOWED_IMPLICIT
        return parse_robots(resp.body), url, RobotsVerdict.ALLOWED_IMPLICIT

    def _load_llms(self, origin: str) -> tuple[Optional[LlmsManifest], Optional[str]]:
        url = manifest_url(origin, "llms.txt")
        resp = self._fetch_text(url)
        if resp is None or resp.status >= 400:
            return None, None
        return parse_llms(resp.body, url), url

    # -- robots decision -------------------------------------------------
    def _robots_decision(
        self,
        policy: RobotsPolicy,
        transport_verdict: RobotsVerdict,
        url: str,
    ) -> RobotsDecision:
        if self.config.robots.mode == "ignore":
            verdict = RobotsVerdict.SKIPPED_BY_USER_POLICY
            match = None
            reason = "robots mode is 'ignore'"
        elif transport_verdict in (
            RobotsVerdict.UNKNOWN_UNREACHABLE,
            RobotsVerdict.UNKNOWN_PARSE_ERROR,
        ):
            verdict = transport_verdict
            match = None
            reason = "robots.txt unreachable or unparseable"
        else:
            verdict, match = evaluate_robots(
                policy, url, self.config.user_agent.product
            )
            reason = f"matched rule on line {match.source_line}" if match else "no matching rule"

        matched_rule = None
        if match is not None:
            matched_rule = {
                "type": "allow" if match.allow else "disallow",
                "pattern": match.pattern,
                "source_line": match.source_line,
            }
        return RobotsDecision(
            verdict=verdict.value,
            user_agent=self.config.user_agent.product,
            requested_url=url,
            recommendation=_RECOMMENDATION_BY_VERDICT[verdict],
            reason=reason,
            matched_rule=matched_rule,
        )

    def _enforce(self, decision: RobotsDecision) -> None:
        if self.config.robots.mode != "respect":
            return
        if decision.verdict in (
            RobotsVerdict.DISALLOWED_EXPLICIT.value,
            RobotsVerdict.UNKNOWN_UNREACHABLE.value,
        ):
            raise PolicyError(
                f"robots policy blocks {decision.requested_url}: "
                f"{decision.verdict} ({decision.reason})"
            )

    # -- AI / llms.txt resolution ---------------------------------------
    def _candidate_allowed(
        self, policy: RobotsPolicy, transport_verdict: RobotsVerdict, url: str
    ) -> bool:
        decision = self._robots_decision(policy, transport_verdict, url)
        return decision.recommendation in ("recommended", "allowed_but_warn")

    def _resolve_ai_target(
        self,
        *,
        requested: str,
        origin: str,
        policy: RobotsPolicy,
        transport_verdict: RobotsVerdict,
        llms_manifest: Optional[LlmsManifest],
        llms_url: Optional[str],
    ) -> tuple[str, str, LlmsDecision, dict[str, str]]:
        """Pick an LLM-friendly fetch target.

        If an ``ai_resolver`` hook is configured, hand it the URL + parsed
        ``llms.txt`` + robots recommendation and let the AI decide the URL
        read-through and any special request headers. Otherwise fall back to
        the built-in rule-based resolver. The chosen URL is always re-checked
        against robots before use.
        """

        strategy = self.config.llms.strategy

        # 1) Injected AI resolver path.
        if self._ai_resolver is not None:
            base_decision = self._robots_decision(policy, transport_verdict, requested)
            hint = self._ai_resolver(
                AiContext(
                    requested_url=requested,
                    origin=origin,
                    llms_manifest=llms_manifest,
                    llms_url=llms_url,
                    robots_recommendation=base_decision.recommendation,
                    robots_verdict=base_decision.verdict,
                )
            )
            if hint is not None:
                target = hint.url or requested
                if target != requested and not self._candidate_allowed(
                    policy, transport_verdict, target
                ):
                    if strategy == "force":
                        raise PolicyError(
                            f"ai_resolver chose {target} but robots disallows it"
                        )
                    target = requested  # robots wins over the AI hint
                selected_by = "llms_txt" if target != requested else "direct"
                if hint.headers:
                    selected_by = "llms_txt"
                return (
                    target,
                    selected_by,
                    LlmsDecision(
                        strategy=strategy,
                        selected_url=target,
                        reason=hint.reason or "ai_resolver hint",
                        resolved_by="ai",
                        applied_headers=dict(hint.headers),
                    ),
                    dict(hint.headers),
                )
            if strategy == "force":
                raise PolicyError("llms strategy is 'force' but ai_resolver gave no hint")

        # 2) Built-in rule-based resolver path.
        chosen: Optional[tuple[str, str]] = None
        for candidate, reason in resolve_candidates(requested, llms_manifest):
            if self._candidate_allowed(policy, transport_verdict, candidate):
                chosen = (candidate, reason)
                break
        if chosen and chosen[0] != requested:
            return (
                chosen[0],
                "llms_txt",
                LlmsDecision(
                    strategy=strategy,
                    selected_url=chosen[0],
                    reason=chosen[1],
                    resolved_by="rule_based",
                ),
                {},
            )
        if strategy == "force" and not chosen:
            raise PolicyError("llms strategy is 'force' but no allowed candidate found")
        return (
            requested,
            "direct",
            LlmsDecision(
                strategy=strategy,
                selected_url=requested,
                reason="no llms-preferred candidate; using original",
                resolved_by="rule_based",
            ),
            {},
        )

    # -- public API ------------------------------------------------------
    def retrieve_url(self, url: str, *, ai_reasoning: bool = False) -> RetrievalResult:
        """Retrieve ``url`` and return a provenance-bearing result."""

        requested = normalize_url(url)
        origin = origin_of(requested)

        policy, robots_url, transport_verdict = self._load_robots(origin)
        llms_manifest: Optional[LlmsManifest] = None
        llms_url: Optional[str] = None
        if ai_reasoning and self.config.llms.strategy != "disabled":
            llms_manifest, llms_url = self._load_llms(origin)

        # Decide the fetch target (and any AI-requested headers).
        final_url = requested
        selected_by = "direct"
        llms_decision: Optional[LlmsDecision] = None
        extra_headers: dict[str, str] = {}

        if ai_reasoning and self.config.llms.strategy != "disabled":
            final_url, selected_by, llms_decision, extra_headers = self._resolve_ai_target(
                requested=requested,
                origin=origin,
                policy=policy,
                transport_verdict=transport_verdict,
                llms_manifest=llms_manifest,
                llms_url=llms_url,
            )

        robots_decision = self._robots_decision(policy, transport_verdict, final_url)
        self._enforce(robots_decision)

        response = self._do_fetch(final_url, headers=extra_headers or None)
        if response.status >= 400:
            raise FetchError(f"fetch returned HTTP {response.status} for {final_url}")

        extracted = self._extractor(response.body, content_type=response.content_type)

        return RetrievalResult(
            request=RequestInfo(input=url, mode="url", timestamp=_now()),
            selected_source=SelectedSource(
                final_url=response.final_url,
                selected_by=selected_by,  # type: ignore[arg-type]
                requested_url=requested,
            ),
            policy=PolicyInfo(robots=robots_decision, llms=llms_decision),
            fetch=FetchInfo(
                status=response.status,
                content_type=response.content_type,
                final_url=response.final_url,
                fetched_at=_now(),
                redirects=response.redirects,
                etag=response.etag,
                last_modified=response.last_modified,
            ),
            extraction=ExtractionInfo(
                extractor="webcanon.basic_html",
                quality_score=extracted.quality_score,
                warnings=extracted.warnings,
            ),
            document=Document(
                markdown=extracted.markdown,
                text=extracted.text,
                title=extracted.title,
                links=extracted.links,
            ),
            provenance=Provenance(
                source_hash=sha256_hex(response.body),
                markdown_hash=sha256_hex(extracted.markdown),
                manifests=ManifestRefs(
                    robots_url=robots_url,
                    llms_url=llms_url,
                    sitemap_urls=[],
                ),
            ),
        )
