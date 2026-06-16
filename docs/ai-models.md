---
title: AI models
nav_order: 8
layout: default
---

# AI models

WebCanon's AI resolver passes the model id straight through to the provider's
SDK, so **any model the provider offers works** — set it with `WEBCANON_AI_MODEL`
or `--ai-model`. The tables below list representative, currently-available model
strings per provider; **bold** is WebCanon's per-provider default.

> The authoritative, always-current list lives in each provider's docs (linked
> per section). Model ids — especially OpenAI's and Gemini's — change often.
> WebCanon does not validate the string: an unknown/retired id makes the
> resolver **decline and fall back to the rule engine** (retrieval still
> succeeds). Check `inspect` → `LLMS: resolved-by` (`ai` vs `rule_based`) to
> confirm the AI ran.

## Picking a model for this task

The AI resolver does one small job per fetch: read the URL + `llms.txt` + robots
verdict and return the URL to fetch and any safe headers. It's a short,
low-stakes tool call — a fast/cheap model is usually plenty.

- **Cost / latency first (recommended):** `gpt-4o-mini`, `gemini-2.5-flash`,
  `claude-haiku-4-5`
- **Maximum quality:** the per-provider defaults below

```bash
webcanon fetch https://example.com/docs/api --ai-provider openai --ai-model gpt-4o-mini
```

## Anthropic (`WEBCANON_AI_PROVIDER=anthropic`)

Key: `ANTHROPIC_API_KEY` · Extra: `pip install "webcanon[ai]"` ·
Docs: <https://docs.anthropic.com/en/docs/about-claude/models>

| Model id | Notes |
| --- | --- |
| `claude-fable-5` | Most capable; hardest reasoning / long-horizon agentic work |
| **`claude-opus-4-8`** (default) | Top Opus-tier; highly autonomous |
| `claude-opus-4-7` | Previous-generation Opus |
| `claude-sonnet-4-6` | Balanced speed and intelligence |
| `claude-haiku-4-5` | Fastest and most cost-effective |

## OpenAI (`WEBCANON_AI_PROVIDER=openai`)

Key: `OPENAI_API_KEY` · Extra: `pip install "webcanon[openai]"` ·
Docs: <https://platform.openai.com/docs/models>

| Model id | Notes |
| --- | --- |
| **`gpt-5`** (default) | Flagship general model |
| `gpt-5-mini` | Smaller, lower-cost `gpt-5` |
| `gpt-4o` | Multimodal general-purpose |
| `gpt-4o-mini` | Small, low-cost `gpt-4o` (good default for this task) |

> Custom / OpenAI-compatible endpoints: set `OPENAI_BASE_URL` or pass
> `OpenAiAiResolver(base_url=...)` in code.

## Google Gemini (`WEBCANON_AI_PROVIDER=gemini`)

Key: `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) ·
Extra: `pip install "webcanon[gemini]"` ·
Docs: <https://ai.google.dev/gemini-api/docs/models>

| Model id | Notes |
| --- | --- |
| **`gemini-2.5-pro`** (default) | Top tier; long context, hardest tasks |
| `gemini-2.5-flash` | Fast, low-cost, balanced |
| `gemini-2.5-flash-lite` | Lightest and cheapest |

## Where the defaults live

The per-provider defaults are defined in `webcanon.ai.DEFAULT_MODELS` and used
whenever `WEBCANON_AI_MODEL` / `--ai-model` is unset. See
[customization.md](customization.md) for provider/key/flag details.
