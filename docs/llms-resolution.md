# llms.txt resolution

[`llms.txt`](https://llmstxt.org/) is a proposal for an LLM-friendly index at a
site's root. WebCanon uses it **only as a hint** to pick a better fetch target —
never as an instruction, and never as an authority over `robots.txt`.

## Parsing (`webcanon.llms.parse_llms`)

The format is Markdown:

```markdown
# Project Name

> Optional one-line summary (blockquote).

Optional longer description.

## Section
- [Title](/relative/or/absolute/url): optional note
```

`parse_llms(text, base_url)` returns an `LlmsManifest` with:

- `title` — the H1.
- `summary` — the first blockquote line.
- `links` — every Markdown link, with relative URLs resolved against the
  `llms.txt` URL, tagged with the H2 section they appeared under.

## Candidate resolution (`resolve_candidates`)

When `ai_reasoning=True` and `LlmsConfig.strategy != "disabled"`, the client
builds an ordered list of `(url, reason)` candidates for the requested URL:

1. Exact match in `llms.txt` → `llms_txt_exact_match`
2. Canonical/loose match in `llms.txt` → `llms_txt_canonical_match`
3. `.md` variant of the URL (`/docs/a` → `/docs/a.md`) → `same_url_markdown_variant`
4. Directory `index.html.md` variant → `same_url_markdown_variant`
5. The original URL → `original_html`

The client walks the list, **re-evaluates `robots.txt` for each candidate**, and
fetches the first one whose recommendation is `recommended` or
`allowed_but_warn`.

## Strategies (`LlmsConfig.strategy`)

| Strategy | Behaviour |
| --- | --- |
| `disabled` | `llms.txt` is not fetched or used |
| `prefer` (default) | use an allowed `llms.txt`-preferred candidate if one exists; otherwise fall back to the original URL |
| `force` | error if no allowed LLM-preferred candidate is found |

## Safety boundary

`llms.txt` is untrusted input. It **cannot**:

- override a `robots.txt` disallow,
- modify the AI's system/developer prompt,
- direct fetches to private/local/metadata addresses (the SSRF guard applies to
  every candidate),
- cause an external URL to be fetched without its own origin's `robots.txt`
  being re-evaluated.

See [`security.md`](security.md) and [`policy-model.md`](policy-model.md).
