from datetime import UTC, datetime

from app.modules.discovery.domain.enums import DiscoveryPriority, DiscoverySource, PageType
from app.modules.discovery.domain.models import ClassificationResult
from app.modules.discovery.domain.reconciliation import DiscoveryCandidate, reconcile

NOW = datetime.now(UTC)


def _candidate(
    *,
    normalized_url: str = "https://example.com/about",
    source: DiscoverySource = DiscoverySource.NAVIGATION,
    source_url: str = "https://example.com/",
    anchor_text: str | None = "About",
    depth: int = 1,
    page_type: PageType = PageType.ABOUT,
    confidence: int = 95,
    rule_id: str = "path:about:/about",
    is_same_domain: bool = True,
    priority: DiscoveryPriority = DiscoveryPriority.PRIORITY_1,
) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        url=normalized_url,
        normalized_url=normalized_url,
        source=source,
        source_url=source_url,
        anchor_text=anchor_text,
        depth=depth,
        classification=ClassificationResult(
            page_type=page_type, confidence=confidence, rule_id=rule_id
        ),
        is_same_domain=is_same_domain,
        priority=priority,
    )


class TestDuplicateMerging:
    def test_two_occurrences_of_same_url_merge_into_one(self) -> None:
        candidates = [_candidate(), _candidate(source=DiscoverySource.SITEMAP, depth=0)]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert len(result) == 1

    def test_distinct_urls_are_not_merged(self) -> None:
        candidates = [
            _candidate(normalized_url="https://example.com/about"),
            _candidate(normalized_url="https://example.com/contact"),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert len(result) == 2


class TestMultipleSourcesRetained:
    def test_sources_are_unioned(self) -> None:
        candidates = [
            _candidate(source=DiscoverySource.NAVIGATION),
            _candidate(source=DiscoverySource.SITEMAP, anchor_text=None),
            _candidate(source=DiscoverySource.FOOTER, anchor_text="About Us"),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        merged = result[0]
        assert set(merged.discovery_sources) == {
            DiscoverySource.NAVIGATION,
            DiscoverySource.SITEMAP,
            DiscoverySource.FOOTER,
        }

    def test_anchor_texts_are_unioned_and_deduplicated(self) -> None:
        candidates = [
            _candidate(anchor_text="About"),
            _candidate(anchor_text="About Us"),
            _candidate(anchor_text="About"),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert result[0].anchor_texts == ["About", "About Us"]

    def test_source_urls_are_unioned(self) -> None:
        candidates = [
            _candidate(source_url="https://example.com/"),
            _candidate(source_url="https://example.com/sitemap.xml"),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert set(result[0].source_urls) == {
            "https://example.com/",
            "https://example.com/sitemap.xml",
        }


class TestStrongestConfidenceSelected:
    def test_higher_confidence_classification_wins(self) -> None:
        candidates = [
            _candidate(page_type=PageType.ABOUT, confidence=95, rule_id="path:about"),
            _candidate(page_type=PageType.CONTACT, confidence=45, rule_id="anchor:contact"),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert result[0].page_type == PageType.ABOUT
        assert result[0].page_type_confidence == 95

    def test_losing_classification_recorded_as_alternate(self) -> None:
        candidates = [
            _candidate(page_type=PageType.ABOUT, confidence=95, rule_id="path:about"),
            _candidate(page_type=PageType.CONTACT, confidence=45, rule_id="anchor:contact"),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        alternates = result[0].metadata.get("alternate_classifications", [])
        assert any(alt["page_type"] == "contact" for alt in alternates)


class TestHighestPriorityRetained:
    def test_priority_1_beats_priority_3(self) -> None:
        candidates = [
            _candidate(priority=DiscoveryPriority.PRIORITY_3),
            _candidate(priority=DiscoveryPriority.PRIORITY_1),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert result[0].priority == DiscoveryPriority.PRIORITY_1

    def test_excluded_loses_to_any_real_priority(self) -> None:
        candidates = [
            _candidate(priority=DiscoveryPriority.EXCLUDED),
            _candidate(priority=DiscoveryPriority.PRIORITY_2),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert result[0].priority == DiscoveryPriority.PRIORITY_2


class TestShallowestDepthRetained:
    def test_minimum_depth_wins(self) -> None:
        candidates = [_candidate(depth=3), _candidate(depth=0), _candidate(depth=1)]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert result[0].depth == 0


class TestOutputFields:
    def test_company_and_run_ids_are_set(self) -> None:
        result = reconcile(
            [_candidate()], company_id="c1", discovery_run_id="r1", discovered_at=NOW
        )
        assert result[0].company_id == "c1"
        assert result[0].discovery_run_id == "r1"

    def test_is_same_domain_true_if_any_candidate_says_so(self) -> None:
        candidates = [
            _candidate(is_same_domain=False),
            _candidate(is_same_domain=True),
        ]
        result = reconcile(candidates, company_id="c1", discovery_run_id="r1", discovered_at=NOW)
        assert result[0].is_same_domain is True
