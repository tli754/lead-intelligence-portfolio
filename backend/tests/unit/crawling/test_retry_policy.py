"""Unit tests for `domain/retry_policy.py` — pure, no I/O."""

from app.modules.crawling.domain.exceptions import DisallowedHostError, TimeoutFetchError
from app.modules.crawling.domain.retry_policy import compute_backoff_delay, is_transient_failure


class TestIsTransientFailure:
    def test_retryable_status_codes(self) -> None:
        for status_code in (408, 425, 429, 500, 502, 503, 504):
            assert is_transient_failure(status_code, None) is True

    def test_non_retryable_status_codes(self) -> None:
        for status_code in (200, 301, 404, 403, 401):
            assert is_transient_failure(status_code, None) is False

    def test_timeout_exception_is_transient(self) -> None:
        assert is_transient_failure(None, TimeoutFetchError("https://example.com")) is True

    def test_connection_reset_is_transient(self) -> None:
        assert is_transient_failure(None, ConnectionResetError()) is True

    def test_disallowed_host_is_not_transient(self) -> None:
        error = DisallowedHostError("https://example.com", reason="private IP")
        assert is_transient_failure(None, error) is False

    def test_no_status_no_exception_is_not_transient(self) -> None:
        assert is_transient_failure(None, None) is False


class TestComputeBackoffDelay:
    def test_delay_grows_exponentially_before_capping(self) -> None:
        delay_1 = compute_backoff_delay(
            1, base_delay_s=1.0, max_delay_s=100.0, jitter_source=lambda: 1.0
        )
        delay_2 = compute_backoff_delay(
            2, base_delay_s=1.0, max_delay_s=100.0, jitter_source=lambda: 1.0
        )
        delay_3 = compute_backoff_delay(
            3, base_delay_s=1.0, max_delay_s=100.0, jitter_source=lambda: 1.0
        )

        assert delay_1 == 1.0
        assert delay_2 == 2.0
        assert delay_3 == 4.0

    def test_delay_is_capped(self) -> None:
        delay = compute_backoff_delay(
            10, base_delay_s=1.0, max_delay_s=5.0, jitter_source=lambda: 1.0
        )
        assert delay == 5.0

    def test_jitter_is_bounded_between_half_and_full(self) -> None:
        low = compute_backoff_delay(
            1, base_delay_s=10.0, max_delay_s=100.0, jitter_source=lambda: 0.0
        )
        high = compute_backoff_delay(
            1, base_delay_s=10.0, max_delay_s=100.0, jitter_source=lambda: 1.0
        )

        assert low == 5.0
        assert high == 10.0

    def test_deterministic_with_injected_jitter_source(self) -> None:
        first = compute_backoff_delay(
            2, base_delay_s=2.0, max_delay_s=100.0, jitter_source=lambda: 0.5
        )
        second = compute_backoff_delay(
            2, base_delay_s=2.0, max_delay_s=100.0, jitter_source=lambda: 0.5
        )
        assert first == second
