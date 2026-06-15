"""Customization hooks: injectable fetcher / extractor / ai_resolver."""

import httpx
import pytest

from webcanon import AiContext, AiHint, WebCanon
from webcanon.config import FetchConfig, RetrievalConfig, UserAgentConfig
from webcanon.errors import PolicyError
from webcanon.extract import ExtractedDocument
from webcanon.fetch import FetchResponse


def test_default_user_agent_is_webcanon():
    assert UserAgentConfig().product == "WebCanon"
    assert UserAgentConfig().header.startswith("WebCanon/")


def _mock_http(routes):
    transport = httpx.MockTransport(routes)
    return httpx.Client(transport=transport, follow_redirects=False)


def test_injected_fetcher_is_used():
    calls = []

    def my_fetcher(url, *, config, user_agent, headers=None):
        calls.append((url, headers))
        return FetchResponse(
            url=url,
            final_url=url,
            status=200,
            content_type="text/html",
            body="<h1>injected</h1>",
        )

    client = WebCanon(
        RetrievalConfig(
            fetcher=my_fetcher,
            fetch=FetchConfig(block_private_addresses=False),
        )
    )
    result = client.retrieve_url("https://example.com/page")
    assert "# injected" in result.document.markdown
    # robots.txt + page both went through the custom fetcher.
    assert any(u.endswith("/robots.txt") for u, _ in calls)
    assert any(u.endswith("/page") for u, _ in calls)


def test_injected_extractor_is_used():
    def my_extractor(body, *, content_type):
        return ExtractedDocument(
            title="custom",
            markdown="CUSTOM-MD",
            text="custom",
            quality_score=0.99,
        )

    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>x</p>")

    client = WebCanon(
        RetrievalConfig(
            extractor=my_extractor,
            fetch=FetchConfig(block_private_addresses=False),
        ),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page")
    assert result.document.markdown == "CUSTOM-MD"
    assert result.extraction.quality_score == 0.99


def test_ai_resolver_receives_llms_and_reroutes_with_headers():
    seen = {}

    def my_ai(ctx: AiContext):
        # The requirement: llms.txt + URL are handed to the AI.
        seen["url"] = ctx.requested_url
        seen["has_llms"] = ctx.llms_manifest is not None
        seen["robots"] = ctx.robots_recommendation
        return AiHint(
            url="https://example.com/docs/api.md",
            headers={"Accept": "text/markdown"},
            reason="ai picked the markdown variant",
        )

    def routes(req):
        path = req.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if path == "/llms.txt":
            return httpx.Response(200, text="# Site\n- [API](/docs/api.md)\n")
        if path == "/docs/api.md":
            assert req.headers.get("Accept") == "text/markdown"  # header applied
            return httpx.Response(
                200, headers={"content-type": "text/markdown"}, text="# API\nbody"
            )
        return httpx.Response(404)

    client = WebCanon(
        RetrievalConfig(
            ai_resolver=my_ai,
            fetch=FetchConfig(block_private_addresses=False),
        ),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)

    assert seen["url"] == "https://example.com/docs/api"
    assert seen["has_llms"] is True
    assert seen["robots"] == "recommended"
    assert result.selected_source.final_url.endswith("/docs/api.md")
    assert result.policy.llms.resolved_by == "ai"
    assert result.policy.llms.applied_headers == {"Accept": "text/markdown"}
    assert "body" in result.document.markdown


def test_ai_hint_cannot_override_robots_disallow():
    def my_ai(ctx):
        return AiHint(url="https://example.com/blocked/doc.md", reason="ai tried")

    def routes(req):
        path = req.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /blocked")
        if path == "/llms.txt":
            return httpx.Response(404)
        if path == "/docs/api":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>ok</p>")
        return httpx.Response(404)

    client = WebCanon(
        RetrievalConfig(
            ai_resolver=my_ai,
            fetch=FetchConfig(block_private_addresses=False),
        ),
        client=_mock_http(routes),
    )
    # robots wins: falls back to the original URL, not the AI's blocked target.
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
    assert result.selected_source.final_url.endswith("/docs/api")
    assert "ok" in result.document.text


def test_ai_resolver_not_called_without_ai_reasoning():
    def my_ai(ctx):
        raise AssertionError("ai_resolver must not run when ai_reasoning=False")

    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>x</p>")

    client = WebCanon(
        RetrievalConfig(ai_resolver=my_ai, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page")  # no ai_reasoning
    assert result.selected_source.selected_by == "direct"
