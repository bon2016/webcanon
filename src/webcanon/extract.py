"""Basic HTML-to-Markdown extraction (stdlib only).

This is the v0.1 baseline extractor described in the memo: sanitize the DOM
(drop script/style/nav/footer/aside), keep headings, paragraphs, lists, code,
blockquotes, and links, then emit Markdown. It also computes a coarse quality
score and surfaces warnings (e.g. hidden text, which can carry prompt
injection). Higher-quality extractors (Readability, headless render,
LLM-assisted repair) plug in behind the same :class:`ExtractedDocument`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from html import unescape

_SKIP_TAGS = {"script", "style", "nav", "footer", "aside", "noscript", "template", "svg"}
_BLOCK_TAGS = {"p", "div", "section", "article", "ul", "ol", "li", "table", "tr"}
_HEADINGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}


@dataclass
class ExtractedDocument:
    title: str | None
    markdown: str
    text: str
    links: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    warnings: list[str] = field(default_factory=list)


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._hidden_depth = 0
        self.title: str | None = None
        self._in_title = False
        self._in_pre = False
        self._list_stack: list[str] = []
        self.links: list[str] = []
        self.hidden_text_found = False

    # -- helpers ---------------------------------------------------------
    def _emit(self, text: str) -> None:
        self._parts.append(text)

    @staticmethod
    def _is_hidden(attrs: list[tuple[str, str | None]]) -> bool:
        for key, value in attrs:
            if value is None:
                continue
            v = value.lower()
            if key == "hidden":
                return True
            if key == "aria-hidden" and v == "true":
                return True
            if key == "style" and ("display:none" in v.replace(" ", "") or
                                    "visibility:hidden" in v.replace(" ", "")):
                return True
        return False

    # -- handlers --------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if self._is_hidden(attrs):
            self._hidden_depth += 1
            self.hidden_text_found = True
            return
        if self._hidden_depth:
            return

        if tag == "title":
            self._in_title = True
        elif tag in _HEADINGS:
            self._emit(f"\n\n{_HEADINGS[tag]} ")
        elif tag == "p":
            self._emit("\n\n")
        elif tag == "br":
            self._emit("  \n")
        elif tag in ("ul", "ol"):
            self._list_stack.append(tag)
            self._emit("\n")
        elif tag == "li":
            indent = "  " * (len(self._list_stack) - 1)
            marker = "- " if (self._list_stack and self._list_stack[-1] == "ul") else "1. "
            self._emit(f"\n{indent}{marker}")
        elif tag in ("pre", "code"):
            if tag == "pre":
                self._in_pre = True
                self._emit("\n\n```\n")
            elif not self._in_pre:
                self._emit("`")
        elif tag == "blockquote":
            self._emit("\n\n> ")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
                self._emit("[")
                self._pending_href = href

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if self._hidden_depth and tag not in _SKIP_TAGS:
            # crude close: assume the hidden block ends at the next close tag
            self._hidden_depth = max(0, self._hidden_depth - 1)
            return

        if tag == "title":
            self._in_title = False
        elif tag in _BLOCK_TAGS and tag not in ("li",):
            self._emit("\n")
            if tag in ("ul", "ol") and self._list_stack:
                self._list_stack.pop()
        elif tag == "pre":
            self._in_pre = False
            self._emit("\n```\n")
        elif tag == "code" and not self._in_pre:
            self._emit("`")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "a":
            href = getattr(self, "_pending_href", None)
            if href:
                self._emit(f"]({href})")
                self._pending_href = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._hidden_depth:
            return
        if self._in_title:
            self.title = (self.title or "") + data.strip()
            return
        if self._in_pre:
            self._emit(data)
        else:
            self._emit(data)

    def markdown(self) -> str:
        text = "".join(self._parts)
        text = unescape(text)
        # Collapse runs of blank lines and trailing spaces.
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _to_plain_text(markdown: str) -> str:
    text = re.sub(r"`{1,3}", "", markdown)
    text = re.sub(r"[#>*_\-]", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_html(html: str, *, content_type: str = "text/html") -> ExtractedDocument:
    """Extract Markdown + plain text from ``html``.

    If ``content_type`` already indicates Markdown/plain text, the body is
    returned mostly verbatim (no DOM processing).
    """

    ct = content_type.lower()
    if "markdown" in ct or ct.startswith("text/plain"):
        warnings: list[str] = []
        return ExtractedDocument(
            title=None,
            markdown=html.strip(),
            text=_to_plain_text(html),
            links=re.findall(r"\]\(([^)]+)\)", html),
            quality_score=1.0,
            warnings=warnings,
        )

    parser = _Extractor()
    parser.feed(html)
    markdown = parser.markdown()
    text = _to_plain_text(markdown)

    warnings = []
    if parser.hidden_text_found:
        warnings.append(
            "hidden_text_detected: page contains hidden elements; "
            "treat as untrusted (possible prompt injection)"
        )

    # Coarse quality score: ratio of extracted text to raw HTML length,
    # clamped to [0, 1]. Real extractors should replace this.
    raw_len = max(len(html), 1)
    score = min(1.0, (len(text) / raw_len) * 4.0)
    if not text:
        score = 0.0

    return ExtractedDocument(
        title=parser.title or None,
        markdown=markdown,
        text=text,
        links=parser.links,
        quality_score=round(score, 3),
        warnings=warnings,
    )
