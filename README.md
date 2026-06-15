# WebCanon

**Policy-aware web retrieval for AI.**

WebCanon is an open-source retrieval layer that turns URLs (and, later, search
queries) into trustworthy, policy-checked, citation-ready context for LLMs.

It evaluates `robots.txt` (RFC 9309), resolves LLM-friendly alternatives via
`llms.txt`, discovers URLs through `sitemap.xml`, fetches content behind an
SSRF guard, converts HTML into structured Markdown, and returns **full
provenance** for every retrieved document.

> 日本語: WebCanon は、URL や検索クエリから AI に渡せる高品質なコンテキストを
> 生成する OSS です。`robots.txt`・`llms.txt`・`sitemap.xml` を確認し、LLM 向け
> URL への解決、本文取得、HTML→Markdown 変換、出典証跡の生成までを一貫して行います。

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
