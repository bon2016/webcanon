# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/) (during `0.x`, MINOR may include
breaking changes).

## [0.4.0] - 2026-06-16

### Added
- **Built-in AI resolvers for three providers, configured via environment
  variables.** `AnthropicAiResolver` (Claude, default `claude-opus-4-8`),
  `OpenAiAiResolver` (default `gpt-5`), and `GeminiAiResolver`
  (default `gemini-2.5-pro`) each reason over the URL + parsed `llms.txt` +
  robots verdict and return a URL read-through plus safe headers.
  `ai_resolver_from_env()` reads `WEBCANON_AI_PROVIDER`
  (`anthropic`/`openai`/`gemini`) / `WEBCANON_AI_MODEL` / the provider's API key
  (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` or
  `GOOGLE_API_KEY`) and returns a resolver or `None`. Optional extras:
  `pip install "webcanon[ai]"` / `"[openai]"` / `"[gemini]"`.
- **Provider/model selection by env var or CLI flag.** New CLI flags
  `--ai-provider {anthropic,openai,gemini}` (implies `--ai`) and `--ai-model`
  take precedence over `WEBCANON_AI_PROVIDER` / `WEBCANON_AI_MODEL`. New public
  helper `build_ai_resolver(provider, model)` and `SUPPORTED_PROVIDERS`.
- **CLI `--ai` uses the configured AI provider** (flags, then env), falling back
  to the built-in rule engine otherwise.
- **Much richer CLI help**: descriptions, per-option explanations, an examples
  section, an AI provider/flag/env reference, and notes (scope, SSRF, User-Agent).

### Changed
- **`document.html` always holds raw HTML (or `None`); `document.markdown`
  always holds Markdown.** When the AI/llms resolver reroutes to a Markdown
  document, the fetched Markdown goes to `document.markdown` and the
  **originally-requested URL's HTML** is fetched separately into
  `document.html`. That second fetch is best-effort and policy-aware: if the
  original URL is robots-disallowed (in `respect` mode), errors, or isn't HTML,
  `document.html` is `None` and the Markdown result still succeeds. A Markdown
  body fetched directly from the requested URL now yields `document.html=None`
  (previously the Markdown was duplicated into `html`).
- New helper `webcanon.extract.is_markdown_content_type()`.

### Security
- The AI's chosen URL is re-evaluated against `robots.txt` and the SSRF guard;
  only allowlisted headers are forwarded. A missing provider package or an
  API/client-init error makes the resolver decline rather than fail retrieval.

### Fixed (review)
- `llms.strategy="force"` no longer fails retrieval when the AI resolver
  declines (transient API error / no hint): it falls back to the rule-based
  resolver and only raises if *no* allowed candidate exists at all.
- Resolvers wrap client construction (not just the API call) and close the SDK
  client after use, so a bad environment declines cleanly and HTTP connection
  pools don't leak for batch/daemon callers.
- AI tool arguments are validated: a non-string `url` becomes `None` and
  non-dict `headers` become `{}` instead of crashing downstream.
- An unknown `WEBCANON_AI_PROVIDER` prints a clean `error: ...` from the CLI
  instead of an uncaught traceback.
- Clarified the CLI help wording for `block_private_addresses` (the guard blocks
  by default; the setting disables it).

## [0.3.0] - 2026-06-16

### Added
- **`document.html`**: every `RetrievalResult` now carries the raw fetched
  source (`result.document.html`) alongside `markdown` and `text`. Included in
  `to_dict()`; intentionally kept out of `to_document()` to keep the RAG shape
  lean.
- **Headless-browser fetcher** for JavaScript-rendered pages:
  `webcanon.headless.PlaywrightFetcher` (optional `webcanon[headless]` extra,
  backed by Playwright). Renders the page in a real browser and returns the
  post-JavaScript HTML. Honours the SSRF guard for the target and final URL and
  the `FetchConfig` limits; raises a clear `FetchError` if Playwright is missing.

### Changed
- Well-known manifests (`robots.txt`, `llms.txt`) always use the lightweight
  built-in HTTP fetcher, even when a heavyweight custom `fetcher` (e.g. a
  headless browser) is configured for the main document.

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

[0.4.0]: https://github.com/bon2016/webcanon/releases/tag/v0.4.0
[0.3.0]: https://github.com/bon2016/webcanon/releases/tag/v0.3.0
[0.2.0]: https://github.com/bon2016/webcanon/releases/tag/v0.2.0
[0.1.0]: https://github.com/bon2016/webcanon/releases/tag/v0.1.0
