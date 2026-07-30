"""Pure per-company request pacing — no I/O, no `asyncio.sleep`.

`RequestPacer` only computes *when* the next request may run, given the
monotonic timestamp of the last request; the actual cancellation-checked
`await asyncio.sleep(...)` lives in
`application/website_crawl_service.py`, keeping this file pure per the
architecture's layering rule.
"""

import time
from collections.abc import Callable

Clock = Callable[[], float]


class RequestPacer:
    """Computes the next monotonic time a request to one company's site
    may run, honoring a configured default/minimum delay and an optional
    robots `Crawl-delay` (already capped by the caller — see
    `domain/robots_policy.py`)."""

    def __init__(
        self,
        *,
        default_delay_s: float,
        min_delay_s: float,
        clock: Clock = time.monotonic,
    ) -> None:
        self._default_delay_s = default_delay_s
        self._min_delay_s = min_delay_s
        self._clock = clock

    def effective_delay(self, *, robots_crawl_delay_s: float | None = None) -> float:
        """The delay to honor before the next request — the larger of the
        configured default delay and an honored robots crawl-delay (both
        floored at the configured minimum)."""
        delay = self._default_delay_s
        if robots_crawl_delay_s is not None:
            delay = max(delay, robots_crawl_delay_s)
        return max(delay, self._min_delay_s)

    def next_allowed_time(
        self, last_request_at: float | None, *, robots_crawl_delay_s: float | None = None
    ) -> float:
        """The monotonic timestamp at/after which the next request may run.

        `last_request_at=None` means no request has been made yet for
        this run — the next request is allowed immediately (the current
        clock reading).
        """
        if last_request_at is None:
            return self._clock()
        return last_request_at + self.effective_delay(robots_crawl_delay_s=robots_crawl_delay_s)

    def now(self) -> float:
        return self._clock()
