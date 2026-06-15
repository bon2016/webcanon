"""Exception hierarchy for WebCanon."""

from __future__ import annotations


class WebCanonError(Exception):
    """Base class for all WebCanon errors."""


class SsrfError(WebCanonError):
    """Raised when a target URL is blocked by the SSRF guard."""


class PolicyError(WebCanonError):
    """Raised when retrieval is forbidden by an evaluated policy.

    For example, ``robots.txt`` disallows the URL while the configured robots
    mode is ``respect``.
    """


class FetchError(WebCanonError):
    """Raised when an HTTP fetch fails irrecoverably."""


class ExtractionError(WebCanonError):
    """Raised when content extraction fails."""
