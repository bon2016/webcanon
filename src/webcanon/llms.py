"""``llms.txt`` parsing and LLM-friendly URL resolution.

``llms.txt`` is a *hint*, never a command and never an authority that can
override ``robots.txt``. We parse the Markdown structure (H1 title, optional
blockquote summary, H2 sections, link lists) and use it only to *suggest*
alternative fetch targets. The pipeline still re-evaluates robots for any URL
chosen this way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlsplit

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_H1_RE = re.compile(r"^#\s+(.*)$")
_H2_RE = re.compile(r"^##\s+(.*)$")


@dataclass
class LlmsLink:
    title: str
    url: str
    section: Optional[str] = None


@dataclass
class LlmsManifest:
    title: Optional[str] = None
    summary: Optional[str] = None
    links: list[LlmsLink] = field(default_factory=list)


def parse_llms(text: str, base_url: str) -> LlmsManifest:
    """Parse an ``llms.txt`` document.

    Relative links are resolved against ``base_url`` (the ``llms.txt`` URL).
    """

    manifest = LlmsManifest()
    section: Optional[str] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if manifest.title is None:
            m = _H1_RE.match(line)
            if m:
                manifest.title = m.group(1).strip()
                continue
        m2 = _H2_RE.match(line)
        if m2:
            section = m2.group(1).strip()
            continue
        if line.startswith(">") and manifest.summary is None:
            manifest.summary = line.lstrip("> ").strip()
            continue
        for match in _LINK_RE.finditer(line):
            title, url = match.group(1).strip(), match.group(2).strip()
            manifest.links.append(
                LlmsLink(title=title, url=urljoin(base_url, url), section=section)
            )
    return manifest


def markdown_variants(url: str) -> list[str]:
    """Candidate Markdown URLs for a page, per the llms.txt proposal.

    * ``https://x/docs/a`` -> ``https://x/docs/a.md``
    * directory URLs -> append ``index.html.md``
    """

    parts = urlsplit(url)
    path = parts.path or "/"
    variants: list[str] = []
    if path.endswith("/"):
        variants.append(url.rstrip("/") + "/index.html.md")
    elif not path.endswith(".md"):
        variants.append(url + ".md")
    return variants


def resolve_candidates(
    requested_url: str,
    manifest: Optional[LlmsManifest],
) -> list[tuple[str, str]]:
    """Return ordered ``(url, reason)`` candidates for an LLM-friendly fetch.

    Ordering follows the memo (section 6.3): exact match in ``llms.txt`` first,
    then ``.md`` variants, then the original URL last. The caller re-evaluates
    robots for each candidate and fetches the first allowed one.
    """

    candidates: list[tuple[str, str]] = []
    if manifest is not None:
        for link in manifest.links:
            if link.url == requested_url:
                candidates.append((link.url, "llms_txt_exact_match"))
            elif link.url.rstrip("/") == requested_url.rstrip("/"):
                candidates.append((link.url, "llms_txt_canonical_match"))
    for variant in markdown_variants(requested_url):
        candidates.append((variant, "same_url_markdown_variant"))
    candidates.append((requested_url, "original_html"))

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for url, reason in candidates:
        if url not in seen:
            seen.add(url)
            unique.append((url, reason))
    return unique
