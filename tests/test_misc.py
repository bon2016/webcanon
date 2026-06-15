"""Tests for url normalization, llms.txt, sitemap, extraction, and SSRF."""

import pytest

from webcanon.errors import SsrfError
from webcanon.extract import extract_html
from webcanon.llms import markdown_variants, parse_llms, resolve_candidates
from webcanon.sitemap import parse_sitemap
from webcanon.ssrf import assert_safe_url
from webcanon.urls import manifest_url, normalize_url, origin_of


# -- urls ---------------------------------------------------------------
def test_normalize_lowercases_and_drops_default_port():
    assert normalize_url("HTTP://Example.com:80/Path") == "http://example.com/Path"


def test_normalize_keeps_nondefault_port_and_drops_fragment():
    assert normalize_url("https://x.com:8443/a#frag") == "https://x.com:8443/a"


def test_origin_and_manifest_url():
    assert origin_of("https://x.com/a/b") == "https://x.com"
    assert manifest_url("https://x.com", "robots.txt") == "https://x.com/robots.txt"


# -- llms.txt -----------------------------------------------------------
def test_parse_llms_extracts_title_and_links():
    text = "# Title\n\n> A summary line\n\n## Docs\n- [API](/docs/api.md)\n"
    manifest = parse_llms(text, "https://x.com/llms.txt")
    assert manifest.title == "Title"
    assert manifest.summary == "A summary line"
    assert manifest.links[0].url == "https://x.com/docs/api.md"
    assert manifest.links[0].section == "Docs"


def test_markdown_variants():
    assert markdown_variants("https://x.com/docs/a") == ["https://x.com/docs/a.md"]
    assert markdown_variants("https://x.com/docs/") == ["https://x.com/docs/index.html.md"]


def test_resolve_candidates_orders_exact_match_first():
    text = "# T\n- [API](https://x.com/docs/api)\n"
    manifest = parse_llms(text, "https://x.com/llms.txt")
    cands = resolve_candidates("https://x.com/docs/api", manifest)
    assert cands[0] == ("https://x.com/docs/api", "llms_txt_exact_match")
    # The original URL is reachable as the first (exact-match) candidate, and
    # a .md variant is also offered.
    urls = [u for u, _ in cands]
    assert "https://x.com/docs/api" in urls
    assert "https://x.com/docs/api.md" in urls


# -- sitemap ------------------------------------------------------------
def test_parse_urlset():
    xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://x.com/a</loc><lastmod>2024-01-01</lastmod></url>
      <url><loc>https://x.com/b</loc></url>
    </urlset>"""
    m = parse_sitemap(xml)
    assert [u.loc for u in m.urls] == ["https://x.com/a", "https://x.com/b"]
    assert m.urls[0].lastmod == "2024-01-01"


def test_parse_sitemap_index():
    xml = """<?xml version="1.0"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://x.com/s1.xml</loc></sitemap>
    </sitemapindex>"""
    m = parse_sitemap(xml)
    assert m.sitemaps == ["https://x.com/s1.xml"]


# -- extraction ---------------------------------------------------------
def test_extract_basic_html():
    html = "<html><head><title>T</title></head><body><h1>Head</h1><p>Hello <a href='/x'>link</a></p><script>bad()</script></body></html>"
    doc = extract_html(html)
    assert doc.title == "T"
    assert "# Head" in doc.markdown
    assert "[link](/x)" in doc.markdown
    assert "bad()" not in doc.markdown
    assert "/x" in doc.links


def test_extract_flags_hidden_text():
    html = "<body><p>visible</p><div style='display:none'>secret instructions</div></body>"
    doc = extract_html(html)
    assert any("hidden_text" in w for w in doc.warnings)


def test_markdown_passthrough():
    doc = extract_html("# already md", content_type="text/markdown")
    assert doc.markdown == "# already md"
    assert doc.quality_score == 1.0


# -- ssrf ---------------------------------------------------------------
def test_ssrf_blocks_loopback():
    with pytest.raises(SsrfError):
        assert_safe_url("http://127.0.0.1/x")


def test_ssrf_blocks_metadata_endpoint():
    with pytest.raises(SsrfError):
        assert_safe_url("http://169.254.169.254/latest/meta-data/")


def test_ssrf_blocks_non_http_scheme():
    with pytest.raises(SsrfError):
        assert_safe_url("file:///etc/passwd")


def test_ssrf_allows_when_private_check_disabled():
    # Scheme is still enforced, but private addresses pass.
    assert_safe_url("http://127.0.0.1/x", block_private=False)
