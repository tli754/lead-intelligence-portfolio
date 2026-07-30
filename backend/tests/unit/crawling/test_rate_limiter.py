"""Unit tests for `domain/rate_limiter.py` — pure, no I/O."""

from app.modules.crawling.domain.rate_limiter import RequestPacer


def _fixed_clock(value: float):
    return lambda: value


class TestFirstRequestIsImmediate:
    def test_no_previous_request_allows_now(self) -> None:
        pacer = RequestPacer(default_delay_s=1.0, min_delay_s=0.5, clock=_fixed_clock(100.0))

        assert pacer.next_allowed_time(None) == 100.0


class TestDefaultDelay:
    def test_subsequent_request_waits_default_delay(self) -> None:
        pacer = RequestPacer(default_delay_s=1.0, min_delay_s=0.5, clock=_fixed_clock(100.0))

        assert pacer.next_allowed_time(50.0) == 51.0


class TestMinimumDelayFloor:
    def test_delay_never_drops_below_minimum(self) -> None:
        pacer = RequestPacer(default_delay_s=0.1, min_delay_s=0.5, clock=_fixed_clock(0.0))

        assert pacer.effective_delay() == 0.5


class TestRobotsCrawlDelayHonored:
    def test_larger_crawl_delay_extends_the_wait(self) -> None:
        pacer = RequestPacer(default_delay_s=1.0, min_delay_s=0.5, clock=_fixed_clock(0.0))

        assert pacer.next_allowed_time(10.0, robots_crawl_delay_s=5.0) == 15.0

    def test_smaller_crawl_delay_does_not_shrink_the_default(self) -> None:
        pacer = RequestPacer(default_delay_s=2.0, min_delay_s=0.5, clock=_fixed_clock(0.0))

        assert pacer.next_allowed_time(10.0, robots_crawl_delay_s=0.1) == 12.0


class TestMonotonicClockUsage:
    def test_now_reads_the_injected_clock(self) -> None:
        pacer = RequestPacer(default_delay_s=1.0, min_delay_s=0.5, clock=_fixed_clock(42.0))

        assert pacer.now() == 42.0
