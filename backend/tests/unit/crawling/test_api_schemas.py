"""Unit tests for `api/schemas.py` — pure, no I/O, no MongoDB."""

from datetime import UTC, datetime

from app.modules.crawling.api.schemas import (
    CrawlRunOptionsRequest,
    CreateCrawlRunRequest,
    page_to_response,
    run_to_response,
    target_to_response,
)
from app.modules.crawling.domain.enums import (
    BrowserPolicy,
    ContentStorageMode,
    CrawlStatus,
    PageFetchStatus,
)
from app.modules.crawling.domain.models import (
    ContentHashes,
    ContentReference,
    ContentStorageInfo,
    CrawledPage,
    CrawlRun,
    CrawlSummary,
    CrawlTarget,
    HttpMetadata,
)
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _run() -> CrawlRun:
    return CrawlRun(
        company_id="company-1",
        discovery_run_id="discovery-1",
        status=CrawlStatus.COMPLETED,
        summary=CrawlSummary(targets_selected=3, pages_fetched=2),
        created_at=NOW,
        updated_at=NOW,
        idempotency_key="key",
    )


def _target() -> CrawlTarget:
    return CrawlTarget(
        crawl_run_id="run-1",
        company_id="company-1",
        discovery_run_id="discovery-1",
        url="https://example.com/",
        normalized_url="https://example.com/",
        page_type=PageType.HOMEPAGE,
        priority=DiscoveryPriority.PRIORITY_1,
        created_at=NOW,
        updated_at=NOW,
    )


def _page(extracted_text: str = "hello world") -> CrawledPage:
    return CrawledPage(
        crawl_run_id="run-1",
        company_id="company-1",
        discovery_run_id="discovery-1",
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        page_type=PageType.HOMEPAGE,
        priority=DiscoveryPriority.PRIORITY_1,
        fetch_status=PageFetchStatus.FETCHED,
        http_metadata=HttpMetadata(status_code=200),
        content_hashes=ContentHashes(raw_content_sha256="abc"),
        content_storage=ContentStorageInfo(
            raw_content_mode=ContentStorageMode.EXTERNAL,
            cleaned_html_mode=ContentStorageMode.INLINE,
        ),
        raw_content_reference=ContentReference(
            reference_id="company-1:run-1:page-1:raw",
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            kind="raw",
        ),
        extracted_text=extracted_text,
        cleaned_html="<h1>hello</h1>",
        created_at=NOW,
        updated_at=NOW,
        fetched_at=NOW,
    )


class TestCamelCaseSerialization:
    def test_run_response_uses_camel_case_keys(self) -> None:
        response = run_to_response(_run())
        dumped = response.model_dump(by_alias=True)

        assert "crawlRunId" in dumped
        assert "discoveryRunId" in dumped
        assert "targetsSelected" in dumped["summary"]

    def test_page_response_uses_camel_case_keys(self) -> None:
        response = page_to_response(_page())
        dumped = response.model_dump(by_alias=True)

        assert "pageId" in dumped
        assert "extractedTextPreview" in dumped
        assert "browserFallbackReason" in dumped


class TestNoFilesystemPathExposure:
    def test_content_reference_is_opaque(self) -> None:
        response = page_to_response(_page())
        assert response.raw_content_reference is not None
        assert response.raw_content_reference.reference_id == "company-1:run-1:page-1:raw"
        assert "/" not in response.raw_content_reference.reference_id.replace(
            "company-1:run-1:page-1:raw", ""
        )

    def test_no_data_crawl_content_path_anywhere_in_response(self) -> None:
        response = page_to_response(_page())
        serialized = response.model_dump_json(by_alias=True)
        assert "data/crawl-content" not in serialized


class TestNoRawHtmlByDefault:
    def test_cleaned_html_is_not_serialized(self) -> None:
        response = page_to_response(_page())
        dumped = response.model_dump(by_alias=True)
        assert "cleanedHtml" not in dumped
        assert "cleaned_html" not in dumped

    def test_extracted_text_preview_is_capped(self) -> None:
        long_text = "x" * 10_000
        response = page_to_response(_page(extracted_text=long_text))

        assert len(response.extracted_text_preview) < len(long_text)
        assert response.extracted_text_truncated is True


class TestPagination:
    def test_target_list_pagination_shape(self) -> None:
        from app.modules.crawling.api.schemas import CrawlTargetListResponse, PaginationMeta

        response = CrawlTargetListResponse(
            data=[target_to_response(_target())],
            pagination=PaginationMeta(page=1, page_size=20, total=1),
        )
        dumped = response.model_dump(by_alias=True)

        assert dumped["pagination"] == {"page": 1, "pageSize": 20, "total": 1}


class TestEnumSerialization:
    def test_status_and_page_type_serialize_as_plain_strings(self) -> None:
        response = target_to_response(_target())
        dumped = response.model_dump(by_alias=True)

        assert dumped["status"] == "queued"
        assert dumped["pageType"] == "homepage"
        assert dumped["priority"] == "1"


class TestRequestParsing:
    def test_request_accepts_camel_case_and_builds_domain_options(self) -> None:
        request = CreateCrawlRunRequest.model_validate(
            {
                "discoveryRunId": "discovery-1",
                "options": {
                    "maxPages": 10,
                    "browserPolicy": "fetch_when_required",
                    "forceRefresh": True,
                    "includePageTypes": ["homepage"],
                    "excludePageTypes": [],
                    "manualUrls": ["https://example.com/x"],
                },
            }
        )

        options = request.options_or_default()
        assert options.max_pages == 10
        assert options.browser_policy == BrowserPolicy.FETCH_WHEN_REQUIRED
        assert options.force_refresh is True
        assert options.manual_urls == ["https://example.com/x"]

    def test_missing_options_defaults_cleanly(self) -> None:
        request = CreateCrawlRunRequest.model_validate({"discoveryRunId": "discovery-1"})
        options = request.options_or_default()

        assert options.max_pages is None
        assert options.manual_urls == []


class TestCrawlRunOptionsRequestDefaults:
    def test_defaults_to_domain_options_cleanly(self) -> None:
        options = CrawlRunOptionsRequest().to_domain()
        assert options.force_refresh is False
        assert options.include_page_types == []
