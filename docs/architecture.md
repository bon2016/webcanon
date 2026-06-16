---
title: Architecture
nav_order: 2
layout: default
---

# Architecture

WebCanon is a **retrieval pipeline + policy engine + evidence log**. Given a URL,
it builds a *verified retrieval plan* (robots → llms.txt → fetch → extract),
executes it, and returns extracted, provenance-bearing content.

> **Scope:** WebCanon's purpose is *correct, policy-aware scraping of a given
> URL*. **Web search engines are out of scope** — finding candidate URLs is a
> separate concern. The pipeline diagram below shows the original vision
> (including a search adapter) for context; the supported entry point is
> `retrieve_url`. Scraping and AI reasoning are **injectable** (see
> [customization.md](customization.md)).

## Pipeline

```text
                ┌──────────────────────┐
                │  User Request         │
                │  URL or Search Query  │
                └──────────┬───────────┘
                           ▼
                ┌──────────────────────┐
                │ Input Router          │  url / search / ai
                └──────────┬───────────┘
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌──────────────┐   ┌────────────────┐   ┌────────────────┐
│ Search       │   │ Origin Manifest│   │ URL Normalizer  │
│ Adapter      │   │ Collector      │   │ Canonicalizer   │
└──────┬───────┘   └───────┬────────┘   └───────┬────────┘
       │                   ▼                    │
       │          ┌────────────────┐            │
       │          │ robots.txt     │            │
       │          │ llms.txt       │            │
       │          │ sitemap.xml    │            │
       │          └───────┬────────┘            │
       └──────────────────┼─────────────────────┘
                          ▼
                ┌──────────────────────┐
                │ Retrieval Planner     │  robots + llms + sitemap
                └──────────┬───────────┘
                           ▼
                ┌──────────────────────┐
                │ Fetch Orchestrator    │  HTTP + SSRF guard
                └──────────┬───────────┘
                           ▼
                ┌──────────────────────┐
                │ Extractor             │  HTML → Markdown
                └──────────┬───────────┘
                           ▼
                ┌──────────────────────┐
                │ Evidence Bundle       │  markdown + provenance
                └──────────────────────┘
```

## Module map (Python)

| Memo concept | Python module | Notes |
| --- | --- | --- |
| URL Normalizer / Canonicalizer | `webcanon.urls` | `normalize_url`, `origin_of`, `manifest_url` |
| Origin Manifest Collector | `webcanon.client` (`_load_robots`, `_load_llms`) | fetches well-known files per origin |
| Robots Policy Engine | `webcanon.robots` | RFC 9309 parser + evaluator (pure, I/O-free) |
| LLMs Resolver | `webcanon.llms` | parse + ordered candidate resolution |
| Sitemap Resolver | `webcanon.sitemap` | urlset + sitemapindex parsing |
| Fetch Orchestrator | `webcanon.fetch` | manual redirects, per-hop SSRF re-check |
| SSRF guard | `webcanon.ssrf` | DNS-resolved IP range checks |
| Extractor | `webcanon.extract` | stdlib HTML → Markdown baseline |
| Evidence / RBOM | `webcanon.types`, `webcanon.provenance` | `RetrievalResult`, sha256 hashes |
| Client / Pipeline | `webcanon.client` | `WebCanon.retrieve_url` |
| CLI | `webcanon.cli` | `fetch`, `inspect` |

## Design principle

> Don't pass search results to the AI. Build a verified retrieval plan from
> them, and pass only fetched, transformed, and provenance-bearing context.

Everything in the pipeline is designed to be **measurable and replaceable**.
Extractors, search providers, and (later) headless renderers plug in behind
narrow interfaces so the *standard layer* stays stable while implementations
improve.

## Roadmap

| Version | Scope |
| --- | --- |
| **v0.1** (this release) | URL retrieval quality baseline: normalize, robots, llms, sitemap, SSRF fetch, basic extraction, provenance, CLI |
| v0.2 | Full `llms.txt` resolution polish, manifest caching with TTL, malicious-`llms.txt` fixtures |
| v0.3 | Framework adapters (LangChain/LlamaIndex/MCP), async path. *(Search adapters are out of scope for this module.)* |
| v0.4 | Readability/Trafilatura extractors, Playwright renderer, table/code preservation, LLM-assisted repair, quality scoring |
| v1.0 | Conformance test suite, stable API, security review, Docker image, docs site, RAG/MCP integrations |