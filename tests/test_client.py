"""End-to-end pipeline tests using an httpx MockTransport (no network)."""

import httpx
import pytest

from webcanon import WebCanon
from webcanon.config import FetchConfig, RetrievalConfig, RobotsConfig
from webcanon.errors import PolicyError


def _make_client(routes, robots_mode="respect"):
    def handler(request: httpx.Request) -> httpx.Response:
        return routes(request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, follow_redirects=False)
    config = RetrievalConfig(
        robots=RobotsConfig(mode=robots_mode),
        # MockTransport never touches DNS, but URLs use example.com anyway.
        fetch=FetchConfig(block_private_addresses=False),
    )
    return WebCanon(config, client=http_client)


def test_basic_fetch_returns_markdown_and_provenance():
    def routes(req):
        path = req.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        if path == "/llms.txt":
            return httpx.Response(404)
        if path == "/page":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><title>Hi</title><body><h1>Title</h1><p>Body</p></body></html>",
            )
        return httpx.Response(404)

    client = _make_client(routes)
    result = client.retrieve_url("https://example.com/page")
    assert result.policy.robots.verdict == "allowed_implicit"
    assert result.policy.robots.recommendation == "recommended"
    assert "# Title" in result.document.markdown
    assert result.document.title == "Hi"
    assert result.provenance.source_hash.startswith("sha256:")
    assert result.selected_source.selected_by == "direct"


def test_disallowed_url_raises_policy_error():
    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="<p>secret</p>")

    client = _make_client(routes)
    with pytest.raises(PolicyError):
        client.retrieve_url("https://example.com/private/secret")


def test_report_only_mode_does_not_block():
    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>ok</p>")

    client = _make_client(routes, robots_mode="report_only")
    result = client.retrieve_url("https://example.com/anything")
    assert result.policy.robots.verdict == "disallowed_explicit"
    assert "ok" in result.document.text


def test_llms_reroute_to_markdown_variant():
    def routes(req):
        path = req.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if path == "/llms.txt":
            return httpx.Response(
                200, text="# Site\n- [API](https://example.com/docs/api.md)\n"
            )
        if path == "/docs/api.md":
            return httpx.Response(
                200, headers={"content-type": "text/markdown"}, text="# API\nmd body"
            )
        if path == "/docs/api":
            return httpx.Response(200, text="<p>html body</p>")
        return httpx.Response(404)

    client = _make_client(routes)
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
    assert result.selected_source.selected_by == "llms_txt"
    assert result.selected_source.final_url.endswith("/docs/api.md")
    assert "md body" in result.document.markdown
