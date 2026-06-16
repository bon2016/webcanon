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
    fetched = []

    def my_ai(ctx):
        # Points at a robots-disallowed URL, plus a header that must be dropped.
        return AiHint(
            url="https://example.com/blocked/doc.md",
            headers={"Accept": "text/markdown"},
            reason="ai tried",
        )

    def routes(req):
        path = req.url.path
        fetched.append(path)
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /blocked")
        if path == "/llms.txt":
            return httpx.Response(404)
        if path == "/blocked/doc.md":
            return httpx.Response(200, text="should never be fetched")
        # Normal resolution continues to the requested URL.
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>ok</p>")

    client = WebCanon(
        RetrievalConfig(
            ai_resolver=my_ai,
            fetch=FetchConfig(block_private_addresses=False),
        ),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
    # robots wins: the disallowed target is never fetched and the whole hint
    # (including its headers) is dropped.
    assert "/blocked/doc.md" not in fetched
    assert not result.selected_source.final_url.endswith("/blocked/doc.md")
    assert result.policy.llms.applied_headers == {}
    assert "ok" in result.document.text


def test_cross_origin_ai_hint_rechecks_target_robots():
    # The AI reroutes to ANOTHER origin whose robots.txt disallows the path.
    # WebCanon must load that origin's robots, not reuse the requested origin's.
    fetched = []

    def my_ai(ctx):
        return AiHint(url="https://other.test/secret", reason="cross-origin")

    def routes(req):
        host = req.url.host
        path = req.url.path
        fetched.append(f"{host}{path}")
        if path == "/robots.txt":
            if host == "other.test":
                return httpx.Response(200, text="User-agent: *\nDisallow: /secret")
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if path == "/llms.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>ok</p>")

    client = WebCanon(
        RetrievalConfig(ai_resolver=my_ai, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
    # other.test's robots.txt was consulted, and the disallowed target avoided.
    assert "other.test/robots.txt" in fetched
    assert "other.test/secret" not in fetched
    assert not result.selected_source.final_url.startswith("https://other.test/secret")


def test_cross_origin_allowed_ai_hint_is_followed():
    def my_ai(ctx):
        return AiHint(url="https://other.test/docs.md", reason="cross-origin ok")

    def routes(req):
        host, path = req.url.host, req.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if path == "/llms.txt":
            return httpx.Response(404)
        if host == "other.test" and path == "/docs.md":
            return httpx.Response(200, headers={"content-type": "text/markdown"}, text="# Other")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>x</p>")

    client = WebCanon(
        RetrievalConfig(ai_resolver=my_ai, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
    assert result.selected_source.final_url == "https://other.test/docs.md"
    assert "# Other" in result.document.markdown


def test_unsafe_injected_headers_are_dropped():
    seen_headers = {}

    def my_ai(ctx):
        return AiHint(
            url=None,
            headers={"Accept": "text/markdown", "Authorization": "Bearer secret",
                     "Cookie": "session=abc"},
            reason="header test",
        )

    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if req.url.path == "/llms.txt":
            return httpx.Response(404)
        seen_headers["authorization"] = req.headers.get("Authorization")
        seen_headers["cookie"] = req.headers.get("Cookie")
        seen_headers["accept"] = req.headers.get("Accept")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>x</p>")

    client = WebCanon(
        RetrievalConfig(ai_resolver=my_ai, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page", ai_reasoning=True)
    # Only the safe Accept header survives; credential-like headers are dropped.
    assert seen_headers["accept"] == "text/markdown"
    assert seen_headers["authorization"] is None
    assert seen_headers["cookie"] is None
    assert result.policy.llms.applied_headers == {"Accept": "text/markdown"}


def test_injected_user_agent_cannot_override_configured_one():
    seen = {}

    def my_ai(ctx):
        # Attempt to spoof the network identity away from robots' UA token.
        return AiHint(headers={"User-Agent": "EvilBot/9", "Accept": "text/markdown"})

    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if req.url.path == "/llms.txt":
            return httpx.Response(404)
        seen["ua"] = req.headers.get("User-Agent")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>x</p>")

    client = WebCanon(
        RetrievalConfig(ai_resolver=my_ai, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    client.retrieve_url("https://example.com/page", ai_reasoning=True)
    assert seen["ua"].startswith("WebCanon/")  # configured UA, not the spoof


def test_custom_extractor_name_is_reported_in_provenance():
    from webcanon.extract import ExtractedDocument

    def my_extractor(body, *, content_type):
        return ExtractedDocument(title=None, markdown="x", text="x", quality_score=0.5)

    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>x</p>")

    client = WebCanon(
        RetrievalConfig(extractor=my_extractor, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page")
    assert result.extraction.extractor.endswith("my_extractor")
    assert result.extraction.extractor != "webcanon.basic_html"


def test_default_extractor_name_unchanged():
    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>x</p>")

    client = WebCanon(
        RetrievalConfig(fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page")
    assert result.extraction.extractor == "webcanon.basic_html"


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
