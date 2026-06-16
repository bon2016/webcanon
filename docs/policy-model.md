---
title: Policy model
nav_order: 3
layout: default
---

# Policy model

WebCanon treats `robots.txt`, `llms.txt`, and `sitemap.xml` as three **distinct**
inputs with three **distinct** authorities. Conflating them is the most common
source of incorrect retrieval behaviour.

| Manifest | Authority | What it decides |
| --- | --- | --- |
| `robots.txt` | **Policy** (RFC 9309) | Whether a URL *should* be fetched |
| `llms.txt` | **Hint** (proposal) | Which alternative URL is *better* for an LLM |
| `sitemap.xml` | **Discovery** | Which URLs *exist* and how fresh they are |

## Hard rules

1. `robots.txt` is evaluated **before** every fetch, including for URLs chosen
   by `llms.txt`.
2. `llms.txt` **cannot** override a `robots.txt` disallow. A candidate URL
   suggested by `llms.txt` is still subject to robots evaluation, and a
   disallowed candidate is skipped.
3. `sitemap.xml` grants **no** fetch permission; it only surfaces URLs.
4. `llms.txt` is **untrusted content**. It is never interpreted as an
   instruction to the AI, and it can never direct fetches to private/local
   addresses (the SSRF guard still applies).
5. When `llms.txt` points to an **external origin**, that origin's `robots.txt`
   is re-evaluated.

## Fetch recommendation

A boolean "allowed/denied" is too coarse. WebCanon returns a
`FetchRecommendation` derived from the robots verdict:

| Situation | Verdict | Recommendation |
| --- | --- | --- |
| Explicit `Allow` | `allowed_explicit` | `recommended` |
| No matching rule | `allowed_implicit` | `recommended` |
| Explicit `Disallow` | `disallowed_explicit` | `not_recommended` |
| `robots.txt` returns 4xx | `allowed_implicit` | `recommended` |
| `robots.txt` returns 5xx / unreachable | `unknown_unreachable` | `unknown_do_not_fetch_by_default` |
| Parse error | `unknown_parse_error` | `allowed_but_warn` |
| Disabled by user policy (`mode=ignore`) | `skipped_by_user_policy` | `recommended` |

## Robots modes

Configured via `RobotsConfig.mode`:

- **`respect`** (default) — a `disallowed_explicit` or `unknown_unreachable`
  verdict raises `PolicyError` and no fetch happens.
- **`report_only`** — the verdict is computed and recorded in the result, but
  never blocks the fetch. Useful for auditing.
- **`ignore`** — `robots.txt` is not fetched at all; verdict is
  `skipped_by_user_policy`.

## `meta robots` / `X-Robots-Tag` (planned)

`robots.txt` governs *crawling*. Page-level `meta name="robots"` and the
`X-Robots-Tag` header govern *indexing/display*. WebCanon will surface these as
**usage/citation warnings** (e.g. `noindex`) rather than as fetch blocks, since
the content has already been retrieved at that point.