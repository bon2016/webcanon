# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/) (during `0.x`, MINOR may include
breaking changes).

## [0.2.0] - 2026-06-16

### Added
- **Customization hooks** on `RetrievalConfig`: injectable `fetcher`,
  `extractor`, and `ai_resolver` callables (`webcanon.hooks` with
  `Fetcher`/`Extractor`/`AiResolver` protocols and `AiContext`/`AiHint`).
- **AI-driven `llms.txt` resolution**: when `ai_reasoning=True` and an
  `ai_resolver` is configured, the URL + parsed `llms.txt` + robots verdict are
  handed to the AI, which can choose a URL read-through and safe request headers.
- **Framework-neutral interop**: `RetrievalResult.to_document()` /
  `to_markdown_with_citation()` and a provider-neutral tool schema in
  `webcanon.schema` (`RETRIEVE_TOOL`, `as_openai_tool`, `as_anthropic_tool`).
- Cross-origin robots re-evaluation for rerouted targets.
- Japanese README (`README.ja.md`) and a GitHub Pages documentation site.

### Changed
- **BREAKING:** the default `User-Agent` product token is now `WebCanon`
  (was `WebCanonBot`). The version segment now tracks the package version.
- `LlmsDecision` records `resolved_by` (`rule_based` / `ai`) and
  `applied_headers`.

### Security
- Injected request headers are restricted to a safe allowlist and dropped on
  cross-origin redirects; an injected `User-Agent` cannot override the
  configured one.
- A robots-disallowed AI hint is dropped in full (URL and headers).

## [0.1.0] - 2026-06-15

### Added
- URL normalization & origin extraction.
- `robots.txt` fetch + RFC 9309 evaluation engine.
- `llms.txt` parsing + rule-based LLM-friendly URL resolution.
- `sitemap.xml` parsing for URL discovery.
- SSRF-guarded HTTP fetch with per-redirect re-checks.
- HTML → Markdown extraction (stdlib) with hidden-text warnings.
- Provenance-bearing `RetrievalResult` (Retrieval Bill of Materials).
- CLI: `webcanon fetch` and `webcanon inspect`.

[0.2.0]: https://github.com/bon2016/webcanon/releases/tag/v0.2.0
[0.1.0]: https://github.com/bon2016/webcanon/releases/tag/v0.1.0
