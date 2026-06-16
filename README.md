# WebCanon

**Policy-aware web retrieval for AI.**

*[日本語版 README はこちら](README.ja.md) — Documentation site: <https://bon2016.github.io/webcanon/>*

WebCanon is an open-source retrieval layer that turns a **URL** into
trustworthy, policy-checked, citation-ready context for LLMs.

It evaluates `robots.txt` (RFC 9309), resolves LLM-friendly alternatives via
`llms.txt` (optionally with your own AI), fetches content behind an SSRF guard,
converts HTML into structured Markdown, and returns **full provenance** for
every retrieved document.

> **Scope:** WebCanon focuses on *correct, policy-aware scraping of a given URL*.
> Web **search engines are out of scope** (finding candidate URLs is a separate
> concern). Scraping and AI reasoning are injectable.

> 日本語: WebCanon は、与えられた URL を AI に渡せる高品質なコンテキストへ変換する
> OSS です。`robots.txt`・`llms.txt`・`sitemap.xml` を確認し、（任意で独自 AI による）
> LLM 向け URL への解決、本文取得、HTML→Markdown 変換、出典証跡の生成までを一貫して
> 行います。WEB 検索エンジンはスコープ外です。スクレイピング処理と AI 処理は差し替え可能です。

## Why

Most AI pipelines mix concerns: they pass raw search snippets to the model,
clone URLs blindly, never check `robots.txt`, ignore `sitemap.xml`, and lose
all provenance. WebCanon separates these into a single quality contract:

| Concept | Role |
| --- | --- |
| Search | Find candidate URLs |
| Fetch | Retrieve URL content |
| Respect | Evaluate `robots.txt` policy before fetching |
| Resolve | Re-route to LLM-friendly URLs via `llms.txt` / canonical |
| Extract | Convert HTML/PDF into LLM-ready Markdown |
| Ground | Keep source, retrieval path, and transform evidence |

### The retrieval constitution

1. Search results are leads, not sources.
2. `robots.txt` is evaluated **before** fetch.
3. `llms.txt` can *guide* retrieval, not override policy.
4. Every transformed document must retain provenance.
5. Web content is **untrusted** input.
6. Markdown is an interface, not the source of truth.
7. Extraction quality must be measurable.

## Install

```bash
pip install webcanon
```

For JavaScript-rendered pages (headless browser, optional):

```bash
pip install "webcanon[headless]"
python -m playwright install chromium
```

For AI-driven `llms.txt` resolution (Anthropic / OpenAI / Gemini, optional):

```bash
pip install "webcanon[ai]"       # anthropic (Claude); or [openai] / [gemini]
```

See [AI providers & API keys](#ai-providers--api-keys) below for how to enable a
provider.

From source:

```bash
pip install -e ".[dev]"
```

## Quick start

```python
from webcanon import WebCanon

client = WebCanon()
result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)

print(result.document.markdown)        # extracted Markdown
print(result.policy.robots.verdict)    # e.g. "allowed_implicit"
print(result.provenance.source_hash)   # sha256 of the source body
```

`result` is a `RetrievalResult` — the **Retrieval Bill of Materials**. Call
`result.to_dict()` for a JSON-serialisable audit record (why this URL was
chosen, whether robots allowed it, whether `llms.txt` rerouted it, extraction
quality, and reproducibility hashes).

The default `User-Agent` product token is **`WebCanon`**.

## Customization hooks

The scraping transport, the HTML→Markdown converter, and the AI that reasons
over `llms.txt` are all **injectable callables** — pass them on
`RetrievalConfig`:

```python
from webcanon import WebCanon, AiHint
from webcanon.config import RetrievalConfig

def my_ai(ctx):
    # ctx has the requested URL, the parsed llms.txt, and the robots verdict.
    # Decide a URL read-through and/or special request headers.
    return AiHint(url=ctx.requested_url + ".md", headers={"Accept": "text/markdown"},
                  reason="prefer markdown variant")

client = WebCanon(RetrievalConfig(
    ai_resolver=my_ai,        # AI reasoning over llms.txt + URL
    # fetcher=my_fetcher,     # custom scraping transport
    # extractor=my_extractor, # custom HTML -> Markdown
))
result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
```

robots.txt always wins: an `AiHint` that points at a disallowed URL is ignored.
See [`docs/customization.md`](docs/customization.md).

## AI providers & API keys

WebCanon ships built-in AI resolvers for three providers. Enable one from the
environment — the CLI (`--ai`) and the library (`ai_resolver_from_env()`) share
the same switch:

| Provider | `WEBCANON_AI_PROVIDER` | **API key env var** | Install extra | Default model | Get a key |
| --- | --- | --- | --- | --- | --- |
| Anthropic (Claude) | `anthropic` | `ANTHROPIC_API_KEY` | `pip install "webcanon[ai]"` | `claude-opus-4-8` | <https://console.anthropic.com/> |
| OpenAI | `openai` | `OPENAI_API_KEY` | `pip install "webcanon[openai]"` | `gpt-5` | <https://platform.openai.com/api-keys> |
| Google Gemini | `gemini` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | `pip install "webcanon[gemini]"` | `gemini-2.5-pro` | <https://aistudio.google.com/apikey> |

Common settings:

- `WEBCANON_AI_PROVIDER` — `anthropic` \| `openai` \| `gemini` to enable; unset
  or `none` to disable (falls back to the built-in rule engine).
- `WEBCANON_AI_MODEL` — override the model id (defaults to the per-provider model
  above).

```bash
# OpenAI
export WEBCANON_AI_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# optional: export WEBCANON_AI_MODEL=gpt-4o
webcanon fetch https://example.com/docs/api --ai

# Google Gemini
export WEBCANON_AI_PROVIDER=gemini
export GEMINI_API_KEY=...           # GOOGLE_API_KEY also works
webcanon fetch https://example.com/docs/api --ai

# Anthropic (Claude)
export WEBCANON_AI_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
webcanon fetch https://example.com/docs/api --ai
```

Notes:

- The AI only *guides* retrieval: its chosen URL is re-checked against
  `robots.txt` and the SSRF guard, and only safe content-negotiation headers
  (`Accept`, …) are sent.
- If the provider's SDK isn't installed or the API errors, the resolver declines
  and WebCanon falls back to the rule engine — retrieval never fails because of AI.
- OpenAI-compatible endpoints: pass `OpenAiAiResolver(base_url=...)` (or set
  `OPENAI_BASE_URL`) when constructing the resolver in code.

## CLI

```bash
webcanon fetch https://example.com/docs/api --ai --llms prefer --robots respect
webcanon fetch https://example.com/docs/api --json --report report.json
webcanon inspect https://example.com/docs/api
```

## Status

This is **v0.1** — the URL retrieval quality baseline:

- URL normalization & origin extraction
- `robots.txt` fetch + RFC 9309 evaluation engine
- `llms.txt` parsing + LLM-friendly URL resolution
- `sitemap.xml` parsing (URL discovery)
- SSRF-guarded HTTP fetch with per-redirect re-checks
- HTML → Markdown extraction (stdlib) with hidden-text warnings
- Provenance-bearing JSON output
- CLI (`fetch`, `inspect`)

See [`docs/`](docs/) for the architecture, policy model, robots compliance,
`llms.txt` resolution, extraction quality, security model, and the roadmap.

## License

Apache-2.0. See [LICENSE](LICENSE).
