"""``webcanon`` command-line interface.

Policy-aware web retrieval for AI. Given a URL, WebCanon evaluates robots.txt
(RFC 9309), optionally resolves an LLM-friendly alternative via llms.txt (with a
built-in rule engine or your own AI), fetches behind an SSRF guard, converts
HTML to Markdown, and returns the content together with the policy verdict and
provenance.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from typing import Optional

from . import __version__
from .ai import ai_resolver_from_env
from .client import WebCanon
from .config import (
    ExtractionConfig,
    LlmsConfig,
    RetrievalConfig,
    RobotsConfig,
)
from .errors import WebCanonError

_EPILOG = textwrap.dedent(
    """\
    examples:
      # Fetch a URL as Markdown (robots.txt respected by default)
      webcanon fetch https://example.com/docs/api

      # Show a human-readable policy report (robots verdict, provenance)
      webcanon inspect https://example.com/docs/api

      # Enable AI/llms.txt resolution and prefer LLM-friendly URLs
      webcanon fetch https://example.com/docs/api --ai --llms prefer

      # Print the full JSON result and also save it to a file
      webcanon fetch https://example.com/docs/api --json --report out.json

      # Audit only: record the robots verdict but never block the fetch
      webcanon fetch https://example.com/private --robots report_only --json

    AI reasoning (optional):
      With --ai, llms.txt is consulted. By default a built-in rule engine picks
      the candidate (exact llms.txt match -> .md variant -> original URL). To let
      an LLM choose the URL and request headers instead, configure a provider via
      environment variables:

        WEBCANON_AI_PROVIDER   anthropic | openai | gemini  (unset/'none' = off)
        WEBCANON_AI_MODEL      model id (per-provider default if unset)
        <provider key>         ANTHROPIC_API_KEY / OPENAI_API_KEY /
                               GEMINI_API_KEY (or GOOGLE_API_KEY)

      Install the matching extra:
        pip install "webcanon[ai]"      # anthropic (Claude)
        pip install "webcanon[openai]"  # openai
        pip install "webcanon[gemini]"  # google gemini

      The AI can only *guide* retrieval: its chosen URL is re-checked against
      robots.txt and the SSRF guard, and only safe headers (Accept, ...) are sent.

    notes:
      * Web search is out of scope; the input is always a specific URL.
      * localhost / private IPs are blocked by the SSRF guard (library only:
        FetchConfig(block_private_addresses=False)).
      * Default User-Agent product token is 'WebCanon'.

    docs: https://bon2016.github.io/webcanon/
    """
)


def _build_client(args: argparse.Namespace) -> WebCanon:
    # Only wire an AI resolver when the user asked for AI reasoning AND a
    # provider is configured in the environment. Otherwise the built-in
    # rule-based resolver is used.
    ai_resolver = None
    if getattr(args, "ai", False):
        ai_resolver = ai_resolver_from_env()
    return WebCanon(
        RetrievalConfig(
            robots=RobotsConfig(mode=args.robots),
            llms=LlmsConfig(strategy=args.llms),
            extraction=ExtractionConfig(format=args.format),
            ai_resolver=ai_resolver,
        )
    )


def _cmd_fetch(args: argparse.Namespace) -> int:
    client = _build_client(args)
    result = client.retrieve_url(args.url, ai_reasoning=args.ai)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2, ensure_ascii=False)
        print(f"wrote report to {args.report}", file=sys.stderr)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    elif args.format == "text":
        print(result.document.text)
    else:
        print(result.document.markdown)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    client = _build_client(args)
    result = client.retrieve_url(args.url, ai_reasoning=args.ai)
    r = result
    lines = [
        f"URL: {r.request.input}",
        "",
        "Selected source:",
        f"  final-url: {r.selected_source.final_url}",
        f"  selected-by: {r.selected_source.selected_by}",
        "",
        "Robots:",
        f"  verdict: {r.policy.robots.verdict if r.policy.robots else 'n/a'}",
        f"  recommendation: {r.policy.robots.recommendation if r.policy.robots else 'n/a'}",
        f"  user-agent: {r.policy.robots.user_agent if r.policy.robots else 'n/a'}",
    ]
    if r.policy.llms:
        lines += [
            "",
            "LLMS:",
            f"  strategy: {r.policy.llms.strategy}",
            f"  resolved-by: {r.policy.llms.resolved_by}",
            f"  selected: {r.policy.llms.selected_url}",
            f"  reason: {r.policy.llms.reason}",
        ]
        if r.policy.llms.applied_headers:
            lines.append(f"  applied-headers: {r.policy.llms.applied_headers}")
    lines += [
        "",
        "Fetch:",
        f"  status: {r.fetch.status}",
        f"  content-type: {r.fetch.content_type}",
        "",
        "Extraction:",
        f"  extractor: {r.extraction.extractor}",
        f"  quality-score: {r.extraction.quality_score}",
    ]
    if r.extraction.warnings:
        lines.append(f"  warnings: {r.extraction.warnings}")
    lines += [
        "",
        "Provenance:",
        f"  source-hash: {r.provenance.source_hash}",
        f"  markdown-hash: {r.provenance.markdown_hash}",
    ]
    print("\n".join(lines))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="webcanon",
        description=(
            "Policy-aware web retrieval for AI: evaluate robots.txt, resolve "
            "llms.txt (optionally with your own AI), fetch behind an SSRF guard, "
            "convert HTML to Markdown, and return provenance."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"webcanon {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("url", help="absolute http(s) URL to retrieve")
        p.add_argument(
            "--ai",
            action="store_true",
            help=(
                "enable llms.txt resolution; uses the AI provider from "
                "WEBCANON_AI_PROVIDER if set, else the built-in rule engine"
            ),
        )
        p.add_argument(
            "--llms",
            choices=["disabled", "prefer", "force"],
            default="prefer",
            metavar="{disabled,prefer,force}",
            help=(
                "llms.txt strategy: disabled (ignore), prefer (use if a better "
                "candidate exists; default), force (error if none allowed)"
            ),
        )
        p.add_argument(
            "--robots",
            choices=["respect", "report_only", "ignore"],
            default="respect",
            metavar="{respect,report_only,ignore}",
            help=(
                "robots.txt handling: respect (block disallowed; default), "
                "report_only (record but never block), ignore (don't fetch robots)"
            ),
        )
        p.add_argument(
            "--format",
            choices=["markdown", "text"],
            default="markdown",
            metavar="{markdown,text}",
            help="output format for the default (non-JSON) print (default: markdown)",
        )

    p_fetch = sub.add_parser(
        "fetch",
        help="retrieve a URL and print the extracted content",
        description="Retrieve a URL and print its Markdown (or text, or full JSON).",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common(p_fetch)
    p_fetch.add_argument(
        "--report",
        metavar="PATH",
        help="write the full JSON result (the Retrieval Bill of Materials) to PATH",
    )
    p_fetch.add_argument(
        "--json",
        action="store_true",
        help="print the full JSON result instead of just the content",
    )
    p_fetch.set_defaults(func=_cmd_fetch)

    p_inspect = sub.add_parser(
        "inspect",
        help="show a human-readable policy/provenance report for a URL",
        description=(
            "Retrieve a URL and print a human-readable report: selected source, "
            "robots verdict, llms.txt resolution, fetch status, extraction "
            "quality, and provenance hashes."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common(p_inspect)
    p_inspect.set_defaults(func=_cmd_inspect)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except WebCanonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
