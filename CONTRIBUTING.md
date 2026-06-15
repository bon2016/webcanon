# Contributing to WebCanon

Thanks for your interest. WebCanon aims to be a *standard layer* for AI web
retrieval, so correctness and clear policy semantics matter more than features.

## Development setup

```bash
# with uv (recommended)
uv run --with pytest --with httpx python -m pytest

# or with pip
python -m pip install -e ".[dev]"
pytest
```

## Project layout

```text
src/webcanon/      # package
  urls.py          # normalization
  ssrf.py          # SSRF guard
  robots.py        # RFC 9309 engine (pure logic)
  llms.py          # llms.txt parser + resolver
  sitemap.py       # sitemap parser
  fetch.py         # HTTP orchestrator
  extract.py       # HTML -> Markdown
  client.py        # pipeline
  cli.py           # CLI
tests/             # pytest suite (no network; uses httpx MockTransport)
docs/              # design + policy docs
```

## Principles (the retrieval constitution)

1. Search results are leads, not sources.
2. `robots.txt` is evaluated before fetch.
3. `llms.txt` can guide retrieval, not override policy.
4. Every transformed document must retain provenance.
5. Web content is untrusted input.
6. Markdown is an interface, not the source of truth.
7. Extraction quality must be measurable.

Changes to policy semantics (robots/llms/sitemap) should come with tests and a
note in the relevant `docs/` file.

## Tests

- Pure logic (`robots`, `urls`, `llms`, `sitemap`, `extract`, `ssrf`) is tested
  without any network.
- Pipeline tests (`tests/test_client.py`) use `httpx.MockTransport`. Do not add
  tests that hit the live network.

## License

By contributing you agree your contributions are licensed under Apache-2.0.
