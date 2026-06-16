---
title: Security
nav_order: 9
layout: default
---

# Security model

WebCanon fetches arbitrary, attacker-influenced URLs and processes
attacker-controlled content. Two threats are treated as first-class:
**SSRF** and **prompt injection**.

## SSRF guard (`webcanon.ssrf`)

`assert_safe_url` is invoked for the target URL **and for every redirect hop**
(`webcanon.fetch` follows redirects manually for exactly this reason).

It blocks:

- Non-HTTP(S) schemes (`file://`, `ftp://`, `gopher://`, …).
- Loopback (`127.0.0.0/8`, `::1`).
- Private ranges (`10/8`, `172.16/12`, `192.168/16`, and IPv6 equivalents).
- Link-local, including the cloud metadata endpoint `169.254.169.254`.
- Multicast, reserved, and unspecified addresses.

The check runs **after DNS resolution**: a public hostname that resolves to a
private IP is still rejected. A literal IP in the URL is checked directly.

Transport limits in `FetchConfig` also bound blast radius: `timeout_seconds`,
`max_redirects`, `max_body_bytes`, and an `allowed_content_types` allowlist.

> `block_private_addresses=False` disables the IP check (scheme is still
> enforced). It exists for tests hitting `localhost` and must not be used in
> production.

## Prompt injection firewall

Every external surface — page body, `llms.txt`, `sitemap.xml`, `robots.txt` —
is **untrusted input**. A page containing `Ignore previous instructions...` must
never change AI behaviour.

WebCanon's responsibilities:

- Return content as **data** (`document.markdown` / `document.text`), with no
  channel through which a page can issue instructions.
- Treat `llms.txt` as a fetch *hint*, never a command
  ([`llms-resolution.md`](llms-resolution.md)).
- Flag **hidden text** during extraction (`hidden`, `aria-hidden`,
  `display:none`, `visibility:hidden`) as a warning, since hidden content is a
  common injection carrier.
- Never fire tool calls from page content.

### AI resolver boundary

The injectable `ai_resolver` ([customization.md](customization.md)) is also
treated as untrusted. Its `AiHint` can *suggest* a fetch target and a few safe
headers, but:

- the chosen URL is re-evaluated against **its own origin's** `robots.txt`
  (cross-origin hints load that host's robots), and disallowed hints are dropped
  in full;
- injected headers are restricted to a safe allowlist and dropped on
  cross-origin redirects, so an `ai_resolver` cannot smuggle `Authorization` /
  `Cookie` headers to another host;
- the SSRF guard applies to every URL the resolver picks.

Callers integrating WebCanon into an LLM **must** keep retrieved content in a
clearly separated channel from the system/developer prompt.

## Reproducibility / provenance

Every result carries `provenance.source_hash` and `provenance.markdown_hash`
(sha256), the manifest URLs consulted, and the selection reason. This is the
Retrieval Bill of Materials — it lets downstream systems audit *why* content was
retrieved and verify it has not changed.

## Reporting a vulnerability

Please report security issues privately to the maintainers rather than opening a
public issue. (Set up a `SECURITY.md` contact / GitHub private advisory before
the first public release.)