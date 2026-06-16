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

## Writing an `ai_resolver`

```python
from webcanon import AiContext, AiHint

def my_ai(ctx: AiContext) -> AiHint | None:
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
