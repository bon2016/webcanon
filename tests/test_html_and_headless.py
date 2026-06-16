"""Tests for document.html and the headless (Playwright) fetcher."""

import httpx
import pytest

from webcanon import PlaywrightFetcher, WebCanon
from webcanon.config import FetchConfig, RetrievalConfig
from webcanon.errors import FetchError, SsrfError


def _mock_http(routes):
    transport = httpx.MockTransport(routes)
    return httpx.Client(transport=transport, follow_redirects=False)


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


def test_markdown_passthrough_still_keeps_html_field():
    def routes(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(200, headers={"content-type": "text/markdown"}, text="# md")

    client = WebCanon(
        RetrievalConfig(fetch=FetchConfig(block_private_addresses=False)),
        client=_mock_http(routes),
    )
    result = client.retrieve_url("https://example.com/page")
    assert result.document.html == "# md"  # the raw body, whatever it was


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
