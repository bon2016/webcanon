---
title: Customization
nav_order: 7
layout: default
---

# Customization hooks

WebCanon's pipeline runs through three replaceable callables. All default to the
built-in implementations; override any of them on `RetrievalConfig`.

| Hook | Type | Replaces | Default |
| --- | --- | --- | --- |
| `fetcher` | `Fetcher` | the scraping transport | `webcanon.fetch.fetch` (SSRF-guarded httpx) |
| `extractor` | `Extractor` | HTML → Markdown conversion | `webcanon.extract.extract_html` |
| `ai_resolver` | `AiResolver` | AI reasoning over `llms.txt` + URL | none (rule-based `resolve_candidates`) |

## Default identity

The default `User-Agent` product token is **`WebCanon`** (`WebCanon/<version>`),
configurable via `UserAgentConfig`.

## The two flows

### URL only (no AI)

1. Fetch `robots.txt`.
2. Evaluate the target URL against it (is `User-agent: *` / our token
   `Disallow`?).
3. Return the scraped content **and** the robots recommendation together.
4. Return rule-based HTML → Markdown together.

```python
result = WebCanon().retrieve_url("https://example.com/page")
result.document.markdown         # rule-based Markdown
result.policy.robots.recommendation  # "recommended" / "not_recommended" / ...
```

### URL + AI enabled (`ai_reasoning=True`)

1. Fetch `robots.txt`.
2. Evaluate the target URL against it.
3. Hand the **URL + parsed `llms.txt` + robots recommendation** to the
   `ai_resolver`. The AI decides how to scrape — e.g. read a different URL, or
   send a specific request header (some docs expose a Markdown variant via an
   `Accept` header or a `.md` URL).
4. Return the content fetched per the AI's decision, the `llms.txt`-derived
   decision, and the robots recommendation.

```python
result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
result.policy.llms.resolved_by      # "ai" or "rule_based"
result.policy.llms.applied_headers  # headers the AI asked us to send
result.selected_source.final_url    # the URL actually fetched
```

If no `ai_resolver` is configured, WebCanon falls back to the built-in
rule-based resolver (exact `llms.txt` match → `.md` variant → original URL).

## Built-in AI resolver (Claude, via environment variables)

WebCanon ships an `ai_resolver` backed by Claude. Enable it from the
environment so the CLI and the library share one switch:

| Variable | Meaning |
| --- | --- |
| `WEBCANON_AI_PROVIDER` | `anthropic` to enable; unset / `none` to disable |
| `WEBCANON_AI_MODEL` | model id (default `claude-opus-4-8`) |
| `ANTHROPIC_API_KEY` | API key for the `anthropic` provider |

Install the optional extra:

```bash
pip install "webcanon[ai]"
```

CLI — `--ai` uses the configured provider automatically (or the rule engine if
none is set):

```bash
export WEBCANON_AI_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
webcanon fetch https://example.com/docs/api --ai
```

Library — `ai_resolver_from_env()` returns the configured resolver or `None`:

```python
from webcanon import WebCanon
from webcanon.ai import ai_resolver_from_env
from webcanon.config import RetrievalConfig

client = WebCanon(RetrievalConfig(ai_resolver=ai_resolver_from_env()))
result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
print(result.policy.llms.resolved_by)  # "ai" when the model rerouted
```

The model is handed the URL + parsed `llms.txt` + robots verdict and returns a
URL read-through plus safe content-negotiation headers. Its choice is **never
trusted**: the URL is re-evaluated against `robots.txt` and the SSRF guard, and
only allowlisted headers are sent (see [security.md](security.md)). If the
`anthropic` package isn't installed or the API errors, the resolver declines
and WebCanon falls back to the rule engine.

## Writing a custom `ai_resolver`

```python
from typing import Optional
from webcanon import AiContext, AiHint

def my_ai(ctx: AiContext) -> Optional[AiHint]:  # Optional keeps it 3.9-compatible
    # ctx.requested_url, ctx.origin
    # ctx.llms_manifest  -> parsed llms.txt (title/summary/links) or None
    # ctx.llms_url       -> the llms.txt URL (or None)
    # ctx.robots_recommendation / ctx.robots_verdict
    if ctx.llms_manifest:
        for link in ctx.llms_manifest.links:
            if link.url.endswith(".md"):
                return AiHint(url=link.url, reason="llms.txt markdown doc")
    return AiHint(headers={"Accept": "text/markdown"}, reason="prefer markdown")
    # return None  => no opinion; proceed normally
```

`AiHint` fields:

- `url` — the URL to fetch (`None` keeps the requested URL).
- `headers` — extra request headers to send.
- `reason` — recorded in `result.policy.llms.reason` (provenance).
- `extra` — free-form dict for your own bookkeeping.

### Policy is never overridden

`robots.txt` is re-evaluated for whatever URL the AI chooses, **against that
URL's own origin** — a cross-origin hint causes the target host's `robots.txt`
to be loaded and evaluated, so a hint can never bypass another site's rules. If
the chosen URL is disallowed, the **entire hint is dropped** (URL *and*
headers) and WebCanon continues with normal resolution (or raises `PolicyError`
when `llms.strategy="force"`). The AI is untrusted: it can *guide* retrieval,
not bypass policy. See [security.md](security.md) and
[policy-model.md](policy-model.md).

### Injected headers are restricted

Headers an `ai_resolver` (or custom caller) supplies are limited to a safe
allowlist (`Accept`, `Accept-Language`, `Accept-Encoding`, `If-None-Match`,
`If-Modified-Since`). Credential-like headers (`Authorization`, `Cookie`, …)
are dropped, and **all injected headers are dropped on cross-origin redirects**
so they cannot leak to another host. `User-Agent` is always sent from
`UserAgentConfig`.

## Writing a `fetcher` / `extractor`

```python
from webcanon.fetch import FetchResponse
from webcanon.extract import ExtractedDocument

def my_fetcher(url, *, config, user_agent, headers=None) -> FetchResponse:
    ...  # MUST still enforce the SSRF guard (see webcanon.ssrf.assert_safe_url)

def my_extractor(body, *, content_type) -> ExtractedDocument:
    ...  # e.g. wrap Trafilatura / Readability
```

A custom `fetcher` is responsible for honouring the SSRF guard and the transport
limits in `config` (timeout, redirects, body size, content types).

## Headless browser (JavaScript-rendered pages)

For single-page apps and client-rendered content, use the built-in
`PlaywrightFetcher`, which renders the page in a real headless browser and
returns the post-JavaScript HTML. Playwright is an **optional** dependency:

```bash
pip install "webcanon[headless]"
python -m playwright install chromium
```

```python
from webcanon import WebCanon
from webcanon.config import RetrievalConfig
from webcanon.headless import PlaywrightFetcher

client = WebCanon(RetrievalConfig(
    fetcher=PlaywrightFetcher(
        browser="chromium",        # or "firefox" / "webkit"
        wait_until="networkidle",  # good default for SPAs
        wait_selector="#app",      # optional: wait for a content container
        extra_wait_ms=0,           # optional fixed delay
    )
))
result = client.retrieve_url("https://example.com/spa")
print(result.document.html)      # rendered HTML
print(result.document.markdown)  # extracted from the rendered DOM
```

It enforces the SSRF guard for the target **and** the final (post-navigation)
URL, and applies the `FetchConfig` timeout and body-size limits. If Playwright
is not installed, it raises a clear `FetchError` telling you how to install it.

## Raw HTML in the result

Every `RetrievalResult` now carries the raw fetched source on
`result.document.html` (alongside `markdown` and `text`), so you can re-extract,
audit, or render the original. It is included in `to_dict()` but **not** in
`to_document()` (the RAG/document shape stays lean).