"""Headless-browser fetcher for JavaScript-rendered pages.

This is an **optional** ``Fetcher`` implementation backed by
`Playwright <https://playwright.dev/python/>`_. It renders the page in a real
(headless) browser and returns the post-JavaScript HTML, so single-page apps
and client-rendered content extract correctly.

Playwright is not a core dependency. Install it with::

    pip install "webcanon[headless]"
    python -m playwright install chromium

Then inject the fetcher::

    from webcanon import WebCanon
    from webcanon.config import RetrievalConfig
    from webcanon.headless import PlaywrightFetcher

    client = WebCanon(RetrievalConfig(fetcher=PlaywrightFetcher()))
    result = client.retrieve_url("https://example.com/spa")
    print(result.document.html)      # rendered HTML
    print(result.document.markdown)  # extracted from the rendered DOM

Like the built-in fetcher, this honours the SSRF guard for the target URL and
the final (post-redirect/navigation) URL, and applies the transport limits in
:class:`webcanon.config.FetchConfig` (timeout, body size, content type).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .config import FetchConfig, UserAgentConfig
from .errors import FetchError
from .fetch import FetchResponse
from .ssrf import assert_safe_url

if TYPE_CHECKING:  # pragma: no cover
    pass

_WAIT_UNTIL = ("load", "domcontentloaded", "networkidle", "commit")


@dataclass
class PlaywrightFetcher:
    """A :class:`webcanon.hooks.Fetcher` that renders pages with Playwright.

    Parameters
    ----------
    browser:
        ``"chromium"`` (default), ``"firefox"``, or ``"webkit"``.
    wait_until:
        Navigation wait condition passed to Playwright
        (``"networkidle"`` by default — waits for the page to go quiet, best
        for SPAs).
    wait_selector:
        Optional CSS selector to wait for after navigation (e.g. a content
        container that appears once JS has run).
    extra_wait_ms:
        Additional fixed delay (milliseconds) after load, for stubborn pages.
    """

    browser: str = "chromium"
    wait_until: str = "networkidle"
    wait_selector: Optional[str] = None
    extra_wait_ms: int = 0

    def __post_init__(self) -> None:
        if self.wait_until not in _WAIT_UNTIL:
            raise ValueError(
                f"wait_until must be one of {_WAIT_UNTIL}, got {self.wait_until!r}"
            )

    def __call__(
        self,
        url: str,
        *,
        config: FetchConfig,
        user_agent: UserAgentConfig,
        headers: Optional[dict[str, str]] = None,
    ) -> FetchResponse:
        # SSRF guard first, before doing any work (including the import).
        assert_safe_url(url, block_private=config.block_private_addresses)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise FetchError(
                "PlaywrightFetcher requires the 'headless' extra. Install with "
                "`pip install \"webcanon[headless]\"` and "
                "`python -m playwright install chromium`."
            ) from exc

        timeout_ms = int(config.timeout_seconds * 1000)
        with sync_playwright() as pw:
            browser_type = getattr(pw, self.browser, None)
            if browser_type is None:
                raise FetchError(f"unknown browser: {self.browser!r}")
            browser = browser_type.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=user_agent.header,
                    extra_http_headers=headers or {},
                )
                page = context.new_page()
                response = page.goto(
                    url, wait_until=self.wait_until, timeout=timeout_ms
                )
                if self.wait_selector:
                    page.wait_for_selector(self.wait_selector, timeout=timeout_ms)
                if self.extra_wait_ms:
                    page.wait_for_timeout(self.extra_wait_ms)

                final_url = page.url
                # Re-check the post-navigation URL against the SSRF guard.
                assert_safe_url(
                    final_url, block_private=config.block_private_addresses
                )

                status = response.status if response is not None else 200
                content_type = ""
                if response is not None:
                    content_type = (
                        response.headers.get("content-type", "").split(";")[0].strip()
                    )
                body = page.content()
                if len(body) > config.max_body_bytes:
                    body = body[: config.max_body_bytes]

                return FetchResponse(
                    url=url,
                    final_url=final_url,
                    status=status,
                    content_type=content_type or "text/html",
                    body=body,
                    redirects=[],
                    etag=response.headers.get("etag") if response else None,
                    last_modified=(
                        response.headers.get("last-modified") if response else None
                    ),
                )
            except FetchError:
                raise
            except Exception as exc:  # pragma: no cover - browser/runtime errors
                raise FetchError(f"headless fetch failed for {url}: {exc}") from exc
            finally:
                browser.close()
