---
title: AI framework affinity
nav_order: 10
layout: default
---

# AI framework affinity

> **Status: analysis & roadmap, not MVP.** This document assesses how readily
> WebCanon (v0.1) integrates into mainstream AI implementation frameworks, and
> defines the small, framework-agnostic surface we should add so that adapters
> for any framework become thin. The integrations themselves are **out of MVP
> scope**; the goal is to make sure nothing in the core design blocks them.

## TL;DR

WebCanon's core is already framework-friendly in the ways that matter most:

- **Pure-Python, narrow dependency** (only `httpx`) — no framework lock-in.
- **A single, well-typed entry point** (`WebCanon.retrieve_url`) returning a
  **serialisable** dataclass (`RetrievalResult.to_dict()`).
- **Provenance and policy carried as data**, which is exactly what RAG / agent
  frameworks want to attach to documents and tool outputs.

What's missing is purely *adaptation surface*: framework base classes, an async
path, a stable string/JSON tool schema, and a couple of convenience shapes
(Document, tool result). None of these require core redesign.

**Current affinity rating (1–5, integration effort to a clean adapter):**

| Framework | Affinity now | Why |
| --- | --- | --- |
| LangChain / LangGraph | ★★★★☆ | Tool & Retriever/DocumentLoader contracts are simple; we already return text + rich metadata. Needs an async path and a thin `BaseTool`/`BaseRetriever` subclass. |
| LlamaIndex | ★★★★☆ | `BaseReader`/`Tool` map cleanly onto `RetrievalResult`; metadata → `Document.metadata`. |
| Model Context Protocol (MCP) | ★★★★★ | A `webcanon.fetch`/`webcanon.inspect` MCP tool is a near-1:1 wrapper over the CLI/JSON we already produce. Highest natural fit. |
| OpenAI / Anthropic tool calling | ★★★★★ | We can emit a JSON-schema tool definition and a JSON result directly; no framework needed. |
| Haystack | ★★★☆☆ | Needs a `@component` wrapper and dataclass→`Document` mapping. Straightforward. |
| CrewAI / AutoGen / Agno etc. | ★★★★☆ | All consume "a callable that takes args and returns text/JSON" — our JSON result is enough; thin wrappers only. |

## What each framework actually requires

Most integrations reduce to one of three shapes. WebCanon should serve all
three from the same core.

### 1. "A tool" (agent function-calling)

A name, a JSON-schema for arguments, a callable, and a (preferably string or
JSON) return value.

- LangChain `BaseTool` / `@tool`; LlamaIndex `FunctionTool`; OpenAI/Anthropic
  tool definitions; MCP `tools/call`; CrewAI/AutoGen tools.
- **WebCanon today:** `retrieve_url(url, ai_reasoning=...)` + `to_dict()`. The
  args and result are already JSON-serialisable. **Gap:** no published tool
  schema, no string-rendering helper, no async variant.

### 2. "A retriever / document loader" (RAG ingestion)

Take a query or URL, return a list of `Document`-like objects with `page_content`
(or `text`) **and** `metadata`.

- LangChain `BaseRetriever` / `BaseLoader`; LlamaIndex `BaseReader`; Haystack
  converters.
- **WebCanon today:** `RetrievalResult.document.markdown` is the content;
  `policy`, `provenance`, `fetch`, `extraction` are ideal `metadata`. **Gap:** no
  `to_document()` convenience shape, no search→multi-doc path (that's v0.3).

### 3. "A service" (HTTP/MCP boundary)

A process exposing fetch/search over a wire protocol so any language/agent can
call it.

- MCP server; a small REST endpoint.
- **WebCanon today:** the CLI emits JSON (`webcanon fetch --json`). **Gap:** no
  MCP server, no REST wrapper (both are thin, post-MVP).

## Concrete gaps to make adapters thin (post-MVP)

These are deliberately **kept out of the core** as optional integration modules
so the dependency stays at `httpx`. Ordered by leverage:

1. **Framework-agnostic result helpers — DONE (in core, zero new deps).**
   Shipped so adapters become one-liners:
   - `RetrievalResult.to_document()` → `{"content"/"page_content"/"text": ...,
     "metadata": {...}}`, a neutral dict every framework maps from.
   - `RetrievalResult.to_markdown_with_citation()` → a string rendering for
     tools that only accept text.
   - A published **JSON tool schema** in `webcanon.schema`
     (`RETRIEVE_TOOL`, `as_openai_tool()`, `as_anthropic_tool()`) describing the
     `webcanon_retrieve` arguments — reused by OpenAI/Anthropic/MCP adapters.

   These are covered by `tests/test_interop.py` and are the proof that the core
   needs **no redesign** to host framework adapters.

2. **Async entry point:** `await WebCanon().aretrieve_url(...)` backed by
   `httpx.AsyncClient`. Required by LangChain/LlamaIndex/MCP async paths and by
   agent runtimes that avoid blocking the event loop. The pure-logic modules
   (`robots`, `llms`, `sitemap`, `extract`) are already sync-safe and reusable as-is.

3. **Optional adapter packages** (extras, not core deps):
   - `webcanon[langchain]` → `WebCanonRetriever(BaseRetriever)`,
     `WebCanonLoader(BaseLoader)`, `webcanon_tool() -> BaseTool`.
   - `webcanon[llamaindex]` → `WebCanonReader(BaseReader)`, a `FunctionTool`.
   - `webcanon[mcp]` → `webcanon-mcp` server exposing `fetch` / `inspect`
     (and `search` after v0.3).
   - `webcanon[haystack]` → a `@component` fetcher/converter.

4. **A provider-neutral tool-call envelope** so the same result feeds OpenAI
   `tool` messages and Anthropic `tool_result` blocks without per-SDK glue.

## Design guarantees we will keep

To stay maximally embeddable across frameworks, the core commits to:

- **Minimal deps:** core depends only on `httpx`. Framework SDKs live behind
  optional extras and are never imported by the core.
- **Stable, serialisable result:** `RetrievalResult` is plain dataclasses;
  `to_dict()` is the contract. New fields are additive.
- **Policy/provenance as data:** never as side effects — so any framework can
  surface them in document metadata or tool output.
- **Sync + async parity:** both call paths share the same pure-logic core.
- **No hidden global state:** an injected `httpx` client is honoured (already
  true), so frameworks can supply their own transport, proxies, and timeouts.

## Mapping cheat-sheet (for future adapter authors)

| WebCanon field | LangChain `Document` | LlamaIndex `Document` | Tool output |
| --- | --- | --- | --- |
| `document.markdown` | `page_content` | `text` | message body |
| `selected_source.final_url` | `metadata["source"]` | `metadata["url"]` | citation URL |
| `policy.robots.verdict` | `metadata["robots"]` | `metadata["robots"]` | policy note |
| `provenance.source_hash` | `metadata["source_hash"]` | `metadata["hash"]` | audit field |
| `extraction.quality_score` | `metadata["quality"]` | `metadata["quality"]` | confidence hint |

See [architecture.md](architecture.md) for the module map and
[publishing.md](publishing.md) for how optional extras will be packaged.