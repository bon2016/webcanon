"""``webcanon`` command-line interface.

Subcommands:

    webcanon fetch <url> [--ai] [--llms prefer|disabled|force]
                          [--robots respect|report_only|ignore]
                          [--format markdown|text] [--report report.json]
    webcanon inspect <url>     # human-readable policy report
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import __version__
from .client import WebCanon
from .config import (
    ExtractionConfig,
    LlmsConfig,
    RetrievalConfig,
    RobotsConfig,
)
from .errors import WebCanonError


def _build_client(args: argparse.Namespace) -> WebCanon:
    return WebCanon(
        RetrievalConfig(
            robots=RobotsConfig(mode=args.robots),
            llms=LlmsConfig(strategy=args.llms),
            extraction=ExtractionConfig(format=args.format),
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
        f"Selected source:",
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
            f"  selected: {r.policy.llms.selected_url}",
            f"  reason: {r.policy.llms.reason}",
        ]
    lines += [
        "",
        "Fetch:",
        f"  status: {r.fetch.status}",
        f"  content-type: {r.fetch.content_type}",
        "",
        "Extraction:",
        f"  extractor: {r.extraction.extractor}",
        f"  quality-score: {r.extraction.quality_score}",
        "",
        f"Provenance:",
        f"  source-hash: {r.provenance.source_hash}",
        f"  markdown-hash: {r.provenance.markdown_hash}",
    ]
    print("\n".join(lines))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="webcanon",
        description="Policy-aware web retrieval for AI.",
    )
    parser.add_argument("--version", action="version", version=f"webcanon {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("url")
        p.add_argument("--ai", action="store_true", help="enable llms.txt resolution")
        p.add_argument(
            "--llms",
            choices=["disabled", "prefer", "force"],
            default="prefer",
        )
        p.add_argument(
            "--robots",
            choices=["respect", "report_only", "ignore"],
            default="respect",
        )
        p.add_argument("--format", choices=["markdown", "text"], default="markdown")

    p_fetch = sub.add_parser("fetch", help="retrieve a URL")
    add_common(p_fetch)
    p_fetch.add_argument("--report", help="write full JSON result to this path")
    p_fetch.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    p_fetch.set_defaults(func=_cmd_fetch)

    p_inspect = sub.add_parser("inspect", help="show a policy report for a URL")
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
