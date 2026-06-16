---
title: Branching & commits
nav_order: 11
layout: default
---

# Branching & commit strategy

## Branch model: GitHub Flow

WebCanon uses a lightweight [GitHub Flow](https://docs.github.com/en/get-started/quickstart/github-flow):

- **`main`** is always releasable. It is the only long-lived branch.
- All work happens on short-lived branches cut from `main` and merged back via
  pull request.
- A release is a **tag** on `main` (`vX.Y.Z`), not a branch.

There is no `develop` branch. The project is small and ships from `main`; a
git-flow style model would add ceremony without benefit at this stage.

### Branch naming

```
<type>/<short-kebab-summary>
```

`type` matches the Conventional Commit types below. Examples:

```
feat/search-adapter-brave
fix/robots-longest-match
docs/extraction-quality
chore/ci-release-workflow
```

## Commits: Conventional Commits

We follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/).

```
<type>(<optional scope>): <description>

<optional body>

<optional footer(s)>
```

### Types

| Type | Use for |
| --- | --- |
| `feat` | a new capability (bumps MINOR) |
| `fix` | a bug fix (bumps PATCH) |
| `docs` | documentation only |
| `test` | adding or fixing tests only |
| `refactor` | behaviour-preserving code change |
| `perf` | performance improvement |
| `build` | build system / packaging (`pyproject.toml`, deps) |
| `ci` | CI configuration |
| `chore` | tooling, repo housekeeping |

### Scopes

Prefer a module/area scope: `robots`, `llms`, `sitemap`, `fetch`, `extract`,
`ssrf`, `cli`, `client`, `urls`, `pkg`, `docs`.

### Breaking changes

Append `!` after the type/scope **and** add a `BREAKING CHANGE:` footer:

```
feat(client)!: rename retrieve_url to retrieve

BREAKING CHANGE: WebCanon.retrieve_url() is now WebCanon.retrieve().
```

This bumps MAJOR (post-1.0) / signals an API break (pre-1.0).

### Examples

```
feat(robots): implement RFC 9309 longest-match evaluation
fix(fetch): re-check SSRF guard on every redirect hop
docs(security): document prompt-injection firewall boundary
build(pkg): configure hatchling build and webcanon entry point
```

## Versioning

[Semantic Versioning](https://semver.org/). During `0.x`, the API is considered
unstable: MINOR may include breaking changes, PATCH is for fixes. The version
lives in **two** places that must stay in sync:

- `pyproject.toml` → `project.version`
- `src/webcanon/__init__.py` → `__version__`

## Pull requests

1. Branch from `main`.
2. Keep the test suite green: `uv run --with pytest --with httpx python -m pytest`.
3. Use a Conventional Commit title for the PR (it becomes the squash-merge
   commit message).
4. Squash-merge to keep `main` history linear and readable.