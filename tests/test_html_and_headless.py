"""Tests for document.html and the headless (Playwright) fetcher."""

import httpx
import pytest

from webcanon import AiHint, PlaywrightFetcher, WebCanon
from webcanon.config import FetchConfig, RetrievalConfig, RobotsConfig
from webcanon.errors import FetchError, SsrfError


def _mock_http(routes):
    transport = httpx.MockTransport(routes)
    return httpx.Client(transport=transport, follow_redirects=False)


def _md_reroute_routes(req):
    """robots allows all; llms.txt lists a .md; original /docs/api is HTML."""
    path = req.url.path
    if path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow:")
    if path == "/llms.txt":
        return httpx.Response(200, text="# Site\n- [API](/docs/api.md)\n")
    if path == "/docs/api.md":
        return httpx.Response(
            200, headers={"content-type": "text/markdown"}, text="# API\nmd body"
        )
    if path == "/docs/api":
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><h1>API</h1></body></html>",
        )
    return httpx.Response(404)


# -- document.html ------------------------------------------------------
def test_document_includes_raw_html():
    raw = "<html><head><title>T</title></head><body><h1>H</h1><p>Body</p></body></html>"

    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(200, headers={"content-type": "text/html"}, text=raw)

    client = WebCanon(
        RetrievalConfig(fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page")
    # Raw source is preserved alongside the extracted markdown/text.
    assert result.document.html == raw
    assert "# H" in result.document.markdown
    # And it round-trips through to_dict().
    assert result.to_dict()["document"]["html"] == raw


def test_markdown_only_fetch_has_no_html():
    # The requested URL itself returns Markdown: markdown holds it, and there is
    # no distinct HTML to capture, so document.html is None.
    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(200, headers={"content-type": "text/markdown"}, text="# md")

    client = WebCanon(
        RetrievalConfig(fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page")
    assert result.document.markdown == "# md"
    assert result.document.html is None


def test_ai_markdown_reroute_keeps_original_html():
    # AI reroutes to a .md doc -> markdown holds the fetched Markdown, and
    # document.html holds the ORIGINAL URL's HTML (fetched separately).
    def my_ai(ctx):
        return AiHint(url="https://example.com/docs/api.md", reason="md variant")

    client = WebCanon(
        RetrievalConfig(ai_resolver=my_ai, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(_md_reroute_routes),
    )
    result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
    assert result.selected_source.final_url.endswith("/docs/api.md")
    assert result.document.markdown == "# API\nmd body"   # fetched Markdown
    assert "<h1>API</h1>" in (result.document.html or "")  # original HTML
    assert result.document.html != result.document.markdown


def test_ai_markdown_reroute_html_none_when_original_disallowed():
    # Original URL is robots-disallowed, but the .md is allowed. We still serve
    # the Markdown; document.html is None (governance-aware, retrieval succeeds).
    def my_ai(ctx):
        return AiHint(url="https://example.com/pub/api.md", reason="md variant")

    def routes(req):
        path = req.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        if path == "/llms.txt":
            return httpx.Response(200, text="# S\n- [API](/pub/api.md)\n")
        if path == "/pub/api.md":
            return httpx.Response(
                200, headers={"content-type": "text/markdown"}, text="# md only"
            )
        if path == "/private/api":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>secret</p>")
        return httpx.Response(404)

    client = WebCanon(
        RetrievalConfig(ai_resolver=my_ai, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/private/api", ai_reasoning=True)
    assert result.document.markdown == "# md only"
    assert result.document.html is None  # original was disallowed → not fetched


def test_ai_html_reroute_stores_html_and_rulebased_markdown():
    # AI reroutes to an HTML doc -> document.html is that HTML, document.markdown
    # is the rule-based conversion (already the behaviour; assert it explicitly).
    def my_ai(ctx):
        return AiHint(url="https://example.com/alt", reason="alt page")

    def routes(req):
        path = req.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if path == "/llms.txt":
            return httpx.Response(404)
        if path == "/alt":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body><h1>Alt</h1><p>body</p></body></html>",
            )
        return httpx.Response(404)

    client = WebCanon(
        RetrievalConfig(ai_resolver=my_ai, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page", ai_reasoning=True)
    assert "<h1>Alt</h1>" in (result.document.html or "")
    assert "# Alt" in result.document.markdown  # rule-based conversion


# -- PlaywrightFetcher --------------------------------------------------
def test_custom_fetcher_never_fetches_manifests():
    # A heavyweight custom fetcher must NOT be used for robots.txt/llms.txt;
    # those always use the lightweight built-in HTTP fetcher.
    from webcanon.fetch import FetchResponse

    seen = []

    def my_fetcher(url, *, config, user_agent, headers=None):
        seen.append(url)
        return FetchResponse(url=url, final_url=url, status=200,
                             content_type="text/html", body="<p>doc</p>")

    def routes(req):
        if req.url.path in ("/robots.txt",):
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if req.url.path == "/llms.txt":
            return httpx.Response(200, text="# Site\n")
        return httpx.Response(404)

    client = WebCanon(
        RetrievalConfig(fetcher=my_fetcher, fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    client.retrieve_url("https://example.com/doc", ai_reasoning=True)
    # The custom fetcher was used only for the document (here the .md variant
    # chosen via llms resolution), never for the manifests.
    assert all(not u.endswith(("/robots.txt", "/llms.txt")) for u in seen)
    assert len(seen) == 1 and seen[0].startswith("https://example.com/doc")


def test_headless_validates_wait_until():
    with pytest.raises(ValueError):
        PlaywrightFetcher(wait_until="whenever")


def test_headless_blocks_ssrf_before_launching_browser():
    fetcher = PlaywrightFetcher()
    # Loopback must be rejected by the SSRF guard regardless of playwright.
    with pytest.raises(SsrfError):
        fetcher(
            "http://127.0.0.1/x",
            config=FetchConfig(block_private_addresses=True),
            user_agent=RetrievalConfig().user_agent,
        )


def test_headless_raises_clear_error_without_playwright():
    pytest.importorskip  # noqa: B018 - just documenting intent
    try:
        import playwright  # noqa: F401

        pytest.skip("playwright is installed; the import-guard path can't be tested")
    except ImportError:
        pass

    fetcher = PlaywrightFetcher()
    with pytest.raises(FetchError) as exc:
        fetcher(
            "https://example.com/",
            config=FetchConfig(block_private_addresses=False),
            user_agent=RetrievalConfig().user_agent,
        )
    assert "headless" in str(exc.value).lower()
