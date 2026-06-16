---
title: Publishing
nav_order: 11
layout: default
---

# Publishing to PyPI

The **primary** release path is automated: pushing a `vX.Y.Z` tag (or publishing
a GitHub Release) triggers `.github/workflows/publish.yml`, which builds, tests,
and publishes to PyPI via **Trusted Publishing (OIDC)** — no API token is stored
in the repo. The manual `twine` flow below is kept as a fallback.

## Automated release (recommended)

One-time setup on PyPI (per project):

1. Create the project's **Trusted Publisher** at
   <https://pypi.org/manage/account/publishing/> (or, for a brand-new name, add a
   *pending* publisher). Use:
   - Owner: `bon2016`  ·  Repository: `webcanon`
   - Workflow: `publish.yml`  ·  Environment: `pypi`
2. In the GitHub repo, create an **Environment** named `pypi`
   (Settings → Environments) — optionally with required reviewers.

Cut a release:

```bash
# 1. Bump version in pyproject.toml AND src/webcanon/__init__.py, update CHANGELOG.
# 2. Merge to main, then tag:
git tag -a v0.2.0 -m "webcanon 0.2.0"
git push origin v0.2.0
```

The workflow then verifies the tag matches the package version, runs the test
suite, builds, `twine check`s, and publishes. Watch it with
`gh run watch` and confirm at <https://pypi.org/project/webcanon/>.

---

## Manual release (fallback)

This requires **your** PyPI credentials and is only needed if the automated
workflow is unavailable.

## 0. Prerequisites

- Python ≥ 3.9 and one of: [`uv`](https://docs.astral.sh/uv/) (used below) or
  `pip` + `build` + `twine`.
- Accounts on [TestPyPI](https://test.pypi.org/) and [PyPI](https://pypi.org/),
  each with **2FA enabled** and an **API token** created
  (Account settings → API tokens).
- The project name `webcanon` must be available on PyPI. **Check first:**
  `https://pypi.org/project/webcanon/`. If taken, change `name` in
  `pyproject.toml` (e.g. one of the memo's alternatives) and the
  `[project.scripts]` / package directory accordingly.

## 1. Build the distributions

```bash
uv build
# or, without uv:
#   python -m pip install build
#   python -m build
```

Produces `dist/webcanon-0.2.0-py3-none-any.whl` and
`dist/webcanon-0.2.0.tar.gz`.

## 2. Validate metadata

```bash
uv run --with twine python -m twine check dist/*
# or: python -m twine check dist/*
```

Both artifacts must report `PASSED`.

## 3. Smoke-test the wheel in a clean environment

```bash
uv run --isolated --no-project --with ./dist/webcanon-0.2.0-py3-none-any.whl \
  webcanon --version
```

Should print `webcanon 0.2.0`.

## 4. Upload to TestPyPI (rehearsal)

```bash
uv run --with twine python -m twine upload --repository testpypi dist/*
```

When prompted for credentials use:

- **username:** `__token__`
- **password:** your TestPyPI API token (the full `pypi-...` string)

Then verify a clean install from TestPyPI (its dependencies live on real PyPI,
so add the extra index):

```bash
uv run --isolated --no-project \
  --index https://test.pypi.org/simple/ \
  --index https://pypi.org/simple/ \
  --with webcanon \
  webcanon --version
```

## 5. Upload to PyPI (real release)

```bash
uv run --with twine python -m twine upload dist/*
```

Use `__token__` / your **PyPI** API token. After it appears on
`https://pypi.org/project/webcanon/`:

```bash
pip install webcanon
```

## 6. Tag the release

```bash
git tag -a v0.2.0 -m "webcanon 0.2.0"
git push origin v0.2.0
```

## Credential storage (recommended)

Avoid pasting tokens interactively. Either use a `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-AgEI...        # your PyPI token

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-AgEN...        # your TestPyPI token
```

…or, for CI, configure **Trusted Publishing** (OIDC) so GitHub Actions can
publish without a long-lived token. See PyPI → project → Settings → Publishing.

## Releasing a new version

1. Bump `version` in `pyproject.toml` **and** `__version__` in
   `src/webcanon/__init__.py`.
2. `rm -rf dist/ && uv build`
3. Repeat steps 2–6.

> A version that has been uploaded to PyPI **cannot be re-uploaded or
> overwritten**. Always rehearse on TestPyPI and bump the version for any fix.