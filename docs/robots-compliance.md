# robots.txt compliance (RFC 9309)

`webcanon.robots` is a pure, I/O-free implementation of the Robots Exclusion
Protocol ([RFC 9309](https://datatracker.ietf.org/doc/rfc9309/)). HTTP status
handling lives in the fetch/client layer; parsing and matching live here so
they can be unit-tested without a network.

## Parsing

- Lines are split on `#` to strip comments, then on the first `:`.
- `User-agent`, `Allow`, `Disallow`, and `Sitemap` records are recognised.
- Consecutive `User-agent` lines (with no rule in between) share the rule block
  that follows them.
- Rules appearing before any `User-agent` are attributed to `*`.

## User-agent matching

```python
policy.rules_for("WebCanonBot")
```

A group token matches the crawler if it is a case-insensitive prefix of (or
substring within) the product token. If any non-`*` group matches, those rules
are merged and used; otherwise the `*` group is the fallback.

## Path matching

`Allow` / `Disallow` patterns support:

- `*` — matches any run of characters.
- `$` — anchors the end of the path (only meaningful as the final character).
- Everything else is matched literally (after `re.escape`).

Matching is evaluated against `path[?query]`, percent-decoded.

### Precedence

1. The **most specific** rule wins, where specificity is the pattern length
   (excluding a trailing `$`).
2. On a length tie, **`Allow` wins** over `Disallow`.
3. An empty `Disallow:` value means "allow everything" and never produces a
   positive match.
4. `/robots.txt` itself is always **implicitly allowed**.

## Transport-level verdicts

Handled in `webcanon.client._load_robots`, per RFC 9309 §2.3.1:

| HTTP result | Meaning | Effect |
| --- | --- | --- |
| 2xx | robots available | parse and evaluate |
| 4xx | robots *unavailable* | treat as "allow all" |
| 5xx / network error / timeout | robots *unreachable* | `unknown_unreachable` → deny by default |

Caching should not exceed 24h (`RobotsConfig.max_cache_seconds`); a persistent
cache is planned for v0.2.

## Worked examples

| robots.txt | URL | Verdict |
| --- | --- | --- |
| `Disallow: /private` | `/private/a` | `disallowed_explicit` |
| `Disallow: /private` | `/public` | `allowed_implicit` |
| `Disallow: /docs` + `Allow: /docs/public` | `/docs/public/a` | `allowed_explicit` |
| `Disallow: /docs` + `Allow: /docs/public` | `/docs/secret` | `disallowed_explicit` |
| `Disallow: /*.pdf$` | `/file.pdf` | `disallowed_explicit` |
| `Disallow: /*.pdf$` | `/file.pdf?x=1` | `allowed_implicit` |

These are exercised in `tests/test_robots.py`.
