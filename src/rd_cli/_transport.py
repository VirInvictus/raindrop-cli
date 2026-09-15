"""The shared HTTP transport core behind both API clients.

Everything here is plumbing both backends need the same way: query-param
encoding (with lowercase booleans, which Raindrop rejects in Python form), the
typed mapping of HTTP errors, the retry waits for ``429``/``5xx``, and one
``send_with_retries`` loop that owns the retry rules. ``RaindropClient`` and
``PinboardClient`` keep their own ``_request`` methods (their auth, dry-run and
pacing differ) but both delegate the sending to this module, so a change to the
retry family lands in exactly one place. That single-site property is the
point: the TimeoutError fix once had to be applied to both clients by hand and
drifted into a duplicated comment until this module existed.
"""

from __future__ import annotations

import calendar
import email.utils
import http.client
import json
import time
import urllib.error
import urllib.parse
from collections.abc import Callable
from typing import Any

from .errors import APIError, AuthError, NotFoundError, RateLimitError

# Transient transport failures worth retrying: every OSError (URLError and
# TimeoutError are subclasses, and ConnectionResetError arrives bare when the
# peer drops the socket) plus http.client's decode failures (IncompleteRead,
# BadStatusLine). HTTPError also subclasses URLError, so it must be caught
# before this family in the send loop.
TRANSIENT: tuple[type[BaseException], ...] = (OSError, http.client.HTTPException)


def backoff(attempt: int) -> float:
    """Exponential backoff: 0.5s, 1s, 2s, ... capped at 30s."""
    return min(0.5 * (2**attempt), 30.0)


def encode_params(params: dict[str, Any] | None) -> str:
    """URL-encode query params, lowercasing booleans (the API rejects ``True``)."""
    if not params:
        return ""
    clean: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            clean[key] = "true" if value else "false"
        else:
            clean[key] = str(value)
    return urllib.parse.urlencode(clean)


def retry_wait(exc: urllib.error.HTTPError, attempt: int) -> float | None:
    """Return seconds to wait before retrying, or ``None`` if not retryable.

    ``429`` honors ``Retry-After`` (integer seconds or an HTTP-date) and
    ``X-RateLimit-Reset`` (both capped at 60s); ``5xx`` uses the backoff
    curve. Any other status (every 4xx, and 3xx when redirects are
    suppressed) is not retried. Shared by both clients so Pinboard honors
    ``Retry-After`` too, not just Raindrop.
    """
    if exc.code == 429:
        header = exc.headers.get("Retry-After")
        if header:
            if header.strip().isdigit():
                return min(float(header), 60.0)
            # Retry-After may also be an HTTP-date.
            parsed = email.utils.parsedate(header)
            if parsed:
                wait = calendar.timegm(parsed) - time.time()
                return max(0.0, min(wait, 60.0))
        reset = exc.headers.get("X-RateLimit-Reset")
        if reset and reset.isdigit():
            return max(0.0, min(float(reset) - time.time(), 60.0))
        return backoff(attempt)
    if 500 <= exc.code < 600:
        return backoff(attempt)
    return None


def network_error(reason: object) -> APIError:
    """The typed error raised when transport retries are exhausted."""
    return APIError(f"Network error: {reason}")


def to_api_error(exc: urllib.error.HTTPError) -> APIError:
    """Map an HTTP error response onto the typed exception family, preferring
    the API's own ``errorMessage``."""
    message = exc.reason or "request failed"
    payload: dict | None = None
    try:
        raw = exc.read()
        if raw:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                payload = decoded
                message = decoded.get("errorMessage") or decoded.get("error") or message
    except (ValueError, OSError):
        pass
    if exc.code in (401, 403):
        return AuthError(message, status=exc.code, payload=payload)
    if exc.code == 404:
        return NotFoundError(message, status=exc.code, payload=payload)
    if exc.code == 429:
        return RateLimitError(message, status=exc.code, payload=payload)
    return APIError(message, status=exc.code, payload=payload)


class _Handled:
    """Sentinel a ``resolve_redirect`` hook returns to answer a response with
    a value instead of a body (possibly ``None``)."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value


def send_with_retries(
    opener: urllib.request.OpenerDirector,
    req: urllib.request.Request,
    *,
    timeout: float,
    max_retries: int,
    sleep: Callable[[float], None],
    http_wait: Callable[[urllib.error.HTTPError, int], float | None],
    transport_retry: bool,
    before_attempt: Callable[[], None] | None = None,
    stamp: Callable[[], None] | None = None,
    resolve_redirect: Callable[[urllib.error.HTTPError], _Handled | None] | None = None,
) -> bytes | str:
    """Send ``req`` and return the raw response body.

    Retries ``429``/``5xx`` while ``http_wait`` returns a wait, and transient
    transport failures (the :data:`TRANSIENT` family) while ``transport_retry``
    holds. Callers pass ``transport_retry=False`` for requests whose
    server-side outcome a retry cannot know: a timed-out POST may already have
    created the object, and re-sending it would double-create silently, so
    writes fail loudly instead.

    ``before_attempt`` runs before every attempt (the Pinboard pacer);
    ``stamp`` runs after every response or HTTP error (the pacer's last-call
    mark). ``resolve_redirect`` may answer an HTTPError with a :class:`_Handled`
    whose value is returned in place of a body (the permanent-copy endpoint's
    307 Location).
    """
    attempt = 0
    while True:
        if before_attempt is not None:
            before_attempt()
        try:
            with opener.open(req, timeout=timeout) as resp:
                body = resp.read()
            if stamp is not None:
                stamp()
            return body
        except urllib.error.HTTPError as exc:
            if stamp is not None:
                stamp()
            if resolve_redirect is not None:
                handled = resolve_redirect(exc)
                if isinstance(handled, _Handled):
                    return handled.value
            wait = http_wait(exc, attempt)
            if wait is not None and attempt < max_retries:
                sleep(wait)
                attempt += 1
                continue
            raise to_api_error(exc) from exc
        except TRANSIENT as exc:
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            if transport_retry and attempt < max_retries:
                sleep(backoff(attempt))
                attempt += 1
                continue
            raise network_error(reason) from exc
