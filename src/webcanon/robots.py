"""RFC 9309 Robots Exclusion Protocol engine.

This is a pure, I/O-free implementation: :func:`parse_robots` turns text into a
:class:`RobotsPolicy`, and :func:`evaluate_robots` decides a single URL against
it. HTTP status handling (4xx => available, 5xx => unreachable) lives in the
fetch layer, which constructs the appropriate verdict.

Matching rules implemented (per RFC 9309 section 2.2.2):

* ``User-agent`` groups are matched case-insensitively against the configured
  product token; the ``*`` group is the fallback.
* All groups whose user-agent matches the crawler are merged.
* ``Allow`` and ``Disallow`` are matched by *longest* path length.
* On an equal-length tie, ``Allow`` wins.
* ``*`` is a wildcard and ``$`` anchors the end of the path.
* The empty ``Disallow:`` value means "allow everything".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import unquote, urlsplit


class RobotsVerdict(str, Enum):
    ALLOWED_EXPLICIT = "allowed_explicit"
    ALLOWED_IMPLICIT = "allowed_implicit"
    DISALLOWED_EXPLICIT = "disallowed_explicit"
    UNKNOWN_UNREACHABLE = "unknown_unreachable"
    UNKNOWN_PARSE_ERROR = "unknown_parse_error"
    SKIPPED_BY_USER_POLICY = "skipped_by_user_policy"


@dataclass
class Rule:
    allow: bool
    pattern: str
    source_line: int


@dataclass
class RobotsPolicy:
    """Parsed ``robots.txt`` ready for evaluation."""

    # user-agent token (lowercased) -> rules
    groups: dict[str, list[Rule]] = field(default_factory=dict)
    sitemaps: list[str] = field(default_factory=list)

    def rules_for(self, product: str) -> list[Rule]:
        """Return merged rules for ``product`` (falls back to ``*``)."""

        product = product.lower()
        # An exact / substring match per RFC 9309: the crawler matches a group
        # if the group token is a case-insensitive prefix of the product.
        matched: list[Rule] = []
        for token, rules in self.groups.items():
            if token == "*":
                continue
            if product.startswith(token) or token in product:
                matched.extend(rules)
        if matched:
            return matched
        return list(self.groups.get("*", []))


def parse_robots(text: str) -> RobotsPolicy:
    """Parse ``robots.txt`` content into a :class:`RobotsPolicy`."""

    policy = RobotsPolicy()
    # Track the user-agents that head the *current* group. Consecutive
    # User-agent lines (with no rule between them) share the following rules.
    current_agents: list[str] = []
    expecting_agent = True

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()

        if field_name == "user-agent":
            if not expecting_agent:
                # Starting a new group; reset.
                current_agents = []
                expecting_agent = True
            agent = value.lower()
            current_agents.append(agent)
            policy.groups.setdefault(agent, [])
        elif field_name in ("allow", "disallow"):
            expecting_agent = False
            if not current_agents:
                # Rule before any user-agent: implicitly applies to '*'.
                current_agents = ["*"]
                policy.groups.setdefault("*", [])
            rule = Rule(
                allow=(field_name == "allow"),
                pattern=value,
                source_line=lineno,
            )
            for agent in current_agents:
                policy.groups[agent].append(rule)
        elif field_name == "sitemap":
            policy.sitemaps.append(value)

    return policy


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a robots path pattern (``*`` wildcard, ``$`` anchor)."""

    out = ["^"]
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            out.append(".*")
        elif ch == "$" and i == n - 1:
            out.append("$")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("".join(out))


def _effective_length(pattern: str) -> int:
    # Per RFC 9309, the most specific rule (longest pattern, by characters,
    # ignoring the trailing anchor) wins.
    return len(pattern.rstrip("$"))


@dataclass
class RobotsMatch:
    allow: bool
    pattern: str
    source_line: int


def _match_path(rules: list[Rule], path: str) -> Optional[RobotsMatch]:
    best: Optional[Rule] = None
    best_len = -1
    for rule in rules:
        if rule.pattern == "" and not rule.allow:
            # 'Disallow:' (empty) => allow all; never a positive match.
            continue
        regex = _pattern_to_regex(rule.pattern) if rule.pattern else re.compile("^")
        if regex.match(path):
            length = _effective_length(rule.pattern)
            if length > best_len or (
                length == best_len and rule.allow and (best is None or not best.allow)
            ):
                best = rule
                best_len = length
    if best is None:
        return None
    return RobotsMatch(allow=best.allow, pattern=best.pattern, source_line=best.source_line)


def evaluate_robots(
    policy: RobotsPolicy,
    url: str,
    product: str,
) -> tuple[RobotsVerdict, Optional[RobotsMatch]]:
    """Evaluate ``url`` for ``product`` against a parsed ``policy``.

    Returns the verdict and the matched rule (if any). ``/robots.txt`` itself
    is always implicitly allowed.
    """

    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    path = unquote(path)

    if path == "/robots.txt":
        return RobotsVerdict.ALLOWED_IMPLICIT, None

    rules = policy.rules_for(product)
    if not rules:
        return RobotsVerdict.ALLOWED_IMPLICIT, None

    match = _match_path(rules, path)
    if match is None:
        return RobotsVerdict.ALLOWED_IMPLICIT, None
    if match.allow:
        return RobotsVerdict.ALLOWED_EXPLICIT, match
    return RobotsVerdict.DISALLOWED_EXPLICIT, match
