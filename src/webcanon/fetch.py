"""HTTP fetch orchestrator with SSRF guard and per-hop redirect checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import httpx

from .config import FetchConfig, UserAgentConfig
from .errors import FetchError
from .ssrf import assert_safe_url


@dataclass
class FetchResponse:
    url: str
    final_url: str
    status: int
    content_type: str
    body: str
    redirects: list[str] = field(default_factory=list)
    etag: Optional[str] = None
    last_modified: Optional[str] = None


def fetch(
    url: str,
    *,
    config: FetchConfig,
    user_agent: UserAgentConfig,
    client: Optional[httpx.Client] = None,
    headers: Optional[dict[str, str]] = None,
) -> FetchResponse:
    """Fetch ``url`` following redirects manually.

    Each redirect target is re-checked by the SSRF guard. Bodies larger than
    ``config.max_body_bytes`` are truncated. Disallowed content types raise
    :class:`FetchError`. ``headers`` are extra per-request headers (e.g. an
    ``Accept`` header requested by an AI resolver); ``User-Agent`` is always
    set from ``user_agent`` unless explicitly overridden here.
    """

    owns_client = client is None
    client = client or httpx.Client(
        follow_redirects=False,
        timeout=config.timeout_seconds,
        headers={"User-Agent": user_agent.header},
    )
    request_headers = {"User-Agent": user_agent.header}
    if headers:
        request_headers.update(headers)
    redirects: list[str] = []
    current = url
    try:
        for _ in range(config.max_redirects + 1):
            assert_safe_url(current, block_private=config.block_private_addresses)
            resp = client.get(current, headers=request_headers)
            if resp.is_redirect and resp.has_redirect_location:
                location = str(resp.next_request.url) if resp.next_request else None
                if not location:
                    break
                redirects.append(location)
                current = location
                continue

            content_type = resp.headers.get("content-type", "").split(";")[0].strip()
            if config.allowed_content_types and content_type and not any(
                content_type == allowed for allowed in config.allowed_content_types
            ):
                raise FetchError(f"content-type not allowed: {content_type}")

            body = resp.content[: config.max_body_bytes]
            text = body.decode(resp.encoding or "utf-8", errors="replace")
            return FetchResponse(
                url=url,
                final_url=str(resp.url),
                status=resp.status_code,
                content_type=content_type or "application/octet-stream",
                body=text,
                redirects=redirects,
                etag=resp.headers.get("etag"),
                last_modified=resp.headers.get("last-modified"),
            )
        raise FetchError(f"too many redirects (> {config.max_redirects})")
    except httpx.HTTPError as exc:
        raise FetchError(f"fetch failed for {current}: {exc}") from exc
    finally:
        if owns_client:
            client.close()
