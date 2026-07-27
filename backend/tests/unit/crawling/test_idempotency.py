"""Unit tests for `domain/idempotency.py` — pure, no I/O."""

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.enums import BrowserPolicy
from app.modules.crawling.domain.idempotency import compute_idempotency_key
from app.modules.crawling.domain.models import CrawlRunOptions
from app.modules.discovery.domain.enums import PageType


class TestDeterministicKey:
    def test_identical_inputs_produce_identical_keys(self) -> None:
        config = CrawlConfig()
        options = CrawlRunOptions(manual_urls=["https://example.com/a"])

        first = compute_idempotency_key("company-1", "discovery-1", config=config, options=options)
        second = compute_idempotency_key("company-1", "discovery-1", config=config, options=options)

        assert first == second

    def test_frozenset_field_ordering_does_not_affect_the_key(self) -> None:
        # Two `CrawlConfig`s with the same *set* of allowlisted headers,
        # built from differently-ordered inputs — the frozenset itself is
        # order-independent, but its JSON-dumped list form is not unless
        # explicitly sorted before hashing.
        config_a = CrawlConfig(response_headers_allowlist=frozenset({"etag", "server"}))
        config_b = CrawlConfig(response_headers_allowlist=frozenset({"server", "etag"}))
        options = CrawlRunOptions()

        key_a = compute_idempotency_key(
            "company-1", "discovery-1", config=config_a, options=options
        )
        key_b = compute_idempotency_key(
            "company-1", "discovery-1", config=config_b, options=options
        )

        assert key_a == key_b


class TestKeyVariesWithInputs:
    def test_different_company_id_changes_the_key(self) -> None:
        config = CrawlConfig()
        options = CrawlRunOptions()

        key_a = compute_idempotency_key("company-1", "discovery-1", config=config, options=options)
        key_b = compute_idempotency_key("company-2", "discovery-1", config=config, options=options)

        assert key_a != key_b

    def test_different_discovery_run_id_changes_the_key(self) -> None:
        config = CrawlConfig()
        options = CrawlRunOptions()

        key_a = compute_idempotency_key("company-1", "discovery-1", config=config, options=options)
        key_b = compute_idempotency_key("company-1", "discovery-2", config=config, options=options)

        assert key_a != key_b

    def test_different_options_changes_the_key(self) -> None:
        config = CrawlConfig()

        key_a = compute_idempotency_key(
            "company-1", "discovery-1", config=config, options=CrawlRunOptions()
        )
        key_b = compute_idempotency_key(
            "company-1",
            "discovery-1",
            config=config,
            options=CrawlRunOptions(force_refresh=True),
        )

        assert key_a != key_b

    def test_manual_urls_order_does_not_matter(self) -> None:
        config = CrawlConfig()
        key_a = compute_idempotency_key(
            "company-1",
            "discovery-1",
            config=config,
            options=CrawlRunOptions(manual_urls=["a", "b"]),
        )
        key_b = compute_idempotency_key(
            "company-1",
            "discovery-1",
            config=config,
            options=CrawlRunOptions(manual_urls=["b", "a"]),
        )

        assert key_a == key_b

    def test_browser_policy_and_page_type_filters_affect_the_key(self) -> None:
        config = CrawlConfig()
        key_a = compute_idempotency_key(
            "company-1",
            "discovery-1",
            config=config,
            options=CrawlRunOptions(browser_policy=BrowserPolicy.DETECT_ONLY),
        )
        key_b = compute_idempotency_key(
            "company-1",
            "discovery-1",
            config=config,
            options=CrawlRunOptions(
                browser_policy=BrowserPolicy.DETECT_ONLY,
                include_page_types=[PageType.HOMEPAGE],
            ),
        )

        assert key_a != key_b
