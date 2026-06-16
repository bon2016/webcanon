---
title: Home
layout: default
nav_order: 1
---

# WebCanon documentation
{: .fs-9 }

Policy-aware web retrieval for AI — `robots.txt`, `llms.txt`, `sitemap.xml`,
fetching, extraction, and provenance in one layer.
{: .fs-6 .fw-300 }

[Get started](#quick-start){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/bon2016/webcanon){: .btn .fs-5 .mb-4 .mb-md-0 }

---

WebCanon turns a **URL** into trustworthy, policy-checked, citation-ready
context for LLMs. It evaluates `robots.txt` (RFC 9309), resolves LLM-friendly
alternatives via `llms.txt` (optionally with your own AI), fetches behind an
SSRF guard, converts HTML into structured Markdown, and returns **full
provenance** for every retrieved document.

> **Scope:** WebCanon focuses on *correct, policy-aware scraping of a given URL*.
> Web search engines are out of scope. Scraping and AI reasoning are injectable.
> 日本語の概要は [README.ja.md](https://github.com/bon2016/webcanon/blob/main/README.ja.md) を参照してください。

## Install

```bash
pip install webcanon
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

## Documentation

| Document | Contents |
| --- | --- |
| [Architecture](architecture.md) | Pipeline overview, module map, roadmap |
| [Policy model](policy-model.md) | How robots / llms / sitemap authorities differ |
| [robots.txt compliance](robots-compliance.md) | RFC 9309 parsing & matching rules |
| [llms.txt resolution](llms-resolution.md) | `llms.txt` parsing & URL resolution |
| [Extraction quality](extraction-quality.md) | HTML→Markdown extraction & quality scoring |
| [Customization](customization.md) | Injectable fetcher / extractor / AI resolver hooks |
| [AI models](ai-models.md) | Supported model strings per provider (Anthropic / OpenAI / Gemini) |
| [Security](security.md) | SSRF guard, prompt-injection firewall, provenance |
| [AI framework affinity](ai-framework-affinity.md) | Fit with LangChain/LlamaIndex/MCP |
| [Branching & commits](branching.md) | Branch model, Conventional Commits, versioning |
| [Publishing](publishing.md) | Step-by-step PyPI release procedure |

## The retrieval constitution

1. Search results are leads, not sources.
2. `robots.txt` is evaluated **before** fetch.
3. `llms.txt` can *guide* retrieval, not override policy.
4. Every transformed document must retain provenance.
5. Web content is **untrusted** input.
6. Markdown is an interface, not the source of truth.
7. Extraction quality must be measurable.
