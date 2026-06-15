"""``sitemap.xml`` parsing for URL discovery (not authorization).

Sitemaps are used purely to *discover* URLs and estimate freshness via
``lastmod``. They never grant fetch permission. Both ``<urlset>`` and
``<sitemapindex>`` documents are supported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from xml.etree import ElementTree


@dataclass
class SitemapEntry:
    loc: str
    lastmod: Optional[str] = None


@dataclass
class SitemapManifest:
    urls: list[SitemapEntry] = field(default_factory=list)
    # Nested sitemap index references (to fetch separately).
    sitemaps: list[str] = field(default_factory=list)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap(text: str) -> SitemapManifest:
    """Parse a sitemap or sitemap index document."""

    manifest = SitemapManifest()
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return manifest

    root_name = _localname(root.tag)
    for child in root:
        name = _localname(child.tag)
        if root_name == "sitemapindex" and name == "sitemap":
            loc = _find_text(child, "loc")
            if loc:
                manifest.sitemaps.append(loc)
        elif root_name == "urlset" and name == "url":
            loc = _find_text(child, "loc")
            if loc:
                manifest.urls.append(
                    SitemapEntry(loc=loc, lastmod=_find_text(child, "lastmod"))
                )
    return manifest


def _find_text(element: ElementTree.Element, local: str) -> Optional[str]:
    for child in element:
        if _localname(child.tag) == local and child.text:
            return child.text.strip()
    return None
