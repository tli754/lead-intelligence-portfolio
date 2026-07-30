"""Pure retry-decision and backoff-delay logic — no I/O, no sleeping.

`is_transient_failure` is checked against already-classified domain
exceptions (`TimeoutFetchError`, a builtin `ConnectionError`), never a raw
`httpx` exception type — keeping this file free of any HTTP-client
dependency. The concrete adapter (`infrastructure/httpx_page_fetcher.py`)
is responsible for translating `httpx`'s own exceptions into these before
calling this function.
"""

import random
from collections.abc import Callable

from app.modules.crawling.domain.config import DEFAULT_RETRYABLE_STATUS_CODES
from app.modules.crawling.domain.exceptions import TimeoutFetchError

JitterSource = Callable[[], float]


def is_transient_failure(
    status_code: int | None,
    exception: BaseException | None = None,
    *,
    retryable_status_codes: frozenset[int] = DEFAULT_RETRYABLE_STATUS_CODES,
) -> bool:
    """Matches the task brief's exact transient-failure list: connection
    reset, timeout, and the configured retryable status codes (default
    408/425/429/500/502/503/504)."""
    if status_code is not None and status_code in retryable_status_codes:
        return True
    if isinstance(exception, TimeoutFetchError):
        return True
    if isinstance(exception, ConnectionError):
        # Covers `ConnectionResetError` (a `ConnectionError` subclass) —
        # stdlib-only, no HTTP-client-specific type.
        return True
    return False


def compute_backoff_delay(
    attempt: int,
    *,
    base_delay_s: float,
    max_delay_s: float,
    jitter_source: JitterSource = random.random,
) -> float:
    """Bounded exponential backoff with jitter.

    `attempt` is 1-indexed (the first retry is `attempt=1`). The delay
    doubles each attempt (`base_delay_s * 2**(attempt-1)`), capped at
    `max_delay_s`, then scaled by a random factor in `[0.5, 1.0]` (a
    "half-jitter" scheme) so retries from many callers don't all land on
    the same instant. `jitter_source` defaults to `random.random` but is
    injectable so tests are deterministic.
    """
    uncapped = base_delay_s * (2 ** max(attempt - 1, 0))
    capped = min(uncapped, max_delay_s)
    jitter_fraction = 0.5 + 0.5 * jitter_source()
    return capped * jitter_fraction
