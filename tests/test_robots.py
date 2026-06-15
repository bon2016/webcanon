"""RFC 9309 robots engine tests (pure logic, no network)."""

from webcanon.robots import RobotsVerdict, evaluate_robots, parse_robots


def _verdict(robots: str, url: str, product: str = "WebCanonBot") -> RobotsVerdict:
    policy = parse_robots(robots)
    verdict, _ = evaluate_robots(policy, url, product)
    return verdict


def test_disallow_explicit():
    robots = "User-agent: *\nDisallow: /private"
    assert _verdict(robots, "https://x.com/private/a") == RobotsVerdict.DISALLOWED_EXPLICIT


def test_allow_implicit_when_no_match():
    robots = "User-agent: *\nDisallow: /private"
    assert _verdict(robots, "https://x.com/public") == RobotsVerdict.ALLOWED_IMPLICIT


def test_longest_match_allow_beats_shorter_disallow():
    robots = "User-agent: *\nDisallow: /docs\nAllow: /docs/public"
    assert _verdict(robots, "https://x.com/docs/public/a") == RobotsVerdict.ALLOWED_EXPLICIT
    assert _verdict(robots, "https://x.com/docs/secret") == RobotsVerdict.DISALLOWED_EXPLICIT


def test_equal_length_tie_allow_wins():
    robots = "User-agent: *\nDisallow: /a\nAllow: /a"
    assert _verdict(robots, "https://x.com/a") == RobotsVerdict.ALLOWED_EXPLICIT


def test_wildcard_and_dollar_anchor():
    robots = "User-agent: *\nDisallow: /*.pdf$"
    assert _verdict(robots, "https://x.com/file.pdf") == RobotsVerdict.DISALLOWED_EXPLICIT
    assert _verdict(robots, "https://x.com/file.pdf?x=1") == RobotsVerdict.ALLOWED_IMPLICIT


def test_empty_disallow_allows_all():
    robots = "User-agent: *\nDisallow:"
    assert _verdict(robots, "https://x.com/anything") == RobotsVerdict.ALLOWED_IMPLICIT


def test_specific_user_agent_group_wins():
    robots = (
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: WebCanonBot\nDisallow: /private\nAllow: /"
    )
    assert _verdict(robots, "https://x.com/public") == RobotsVerdict.ALLOWED_EXPLICIT
    assert _verdict(robots, "https://x.com/private") == RobotsVerdict.DISALLOWED_EXPLICIT


def test_robots_txt_itself_is_implicitly_allowed():
    robots = "User-agent: *\nDisallow: /"
    assert _verdict(robots, "https://x.com/robots.txt") == RobotsVerdict.ALLOWED_IMPLICIT


def test_sitemap_directive_collected():
    policy = parse_robots("Sitemap: https://x.com/sitemap.xml\nUser-agent: *\nDisallow:")
    assert policy.sitemaps == ["https://x.com/sitemap.xml"]
