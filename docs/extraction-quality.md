---
title: Extraction quality
nav_order: 6
layout: default
---

# Extraction quality

Extraction turns fetched bytes into LLM-ready Markdown **plus** a quality signal.
WebCanon treats extraction as a *measurable, replaceable* step, not a one-shot
HTML→Markdown call.

## v0.1 baseline (`webcanon.extract`)

The shipped extractor uses only the standard library (`html.parser`). It:

- Drops non-content tags: `script`, `style`, `nav`, `footer`, `aside`,
  `noscript`, `template`, `svg`.
- Preserves headings (`#`–`######`), paragraphs, lists (nested), `pre`/`code`
  blocks, blockquotes, bold/italic, and links (`[text](href)`).
- Extracts the `<title>`.
- Collects all link hrefs into `document.links`.
- Detects **hidden text** (`hidden`, `aria-hidden="true"`,
  `display:none`, `visibility:hidden`) and raises a warning — hidden content is
  a common prompt-injection vector (see [`security.md`](security.md)).
- Returns a coarse `quality_score` in `[0, 1]` based on the ratio of extracted
  text to raw HTML length.

If the response is already Markdown or plain text (`content_type` indicates
`markdown`/`text/plain`), the body is passed through with `quality_score = 1.0`.

## Quality dimensions (planned)

Higher-quality extractors should report a structured score:

| Dimension | Question |
| --- | --- |
| Extraction rate | How much main content survived boilerplate removal? |
| Link preservation | Were in-content links kept? |
| Table preservation | Were tables rendered as Markdown tables? |
| Code preservation | Were code blocks kept verbatim? |
| Duplication | Is repeated boilerplate present? |

## Pluggable extractors (planned)

The standard layer is the interface, not the implementation. Future extractors
plug in behind a common shape and are selected per input:

```python
class Extractor(Protocol):
    name: str
    def can_handle(self, response) -> bool: ...
    def extract(self, response) -> ExtractedDocument: ...
```

Planned implementations: Readability, Trafilatura, a Playwright headless
renderer for JS-heavy pages, and an optional LLM-assisted repair pass for DOMs
that defeat rule-based extraction.

## Conformance fixtures (planned)

A `fixtures/html/` corpus (`article-basic`, `docs-page`, `ecommerce-product`,
`spa-rendered`, `table-heavy`, `hostile-hidden-text`) will pin extraction
behaviour across extractors so the standard stays comparable.