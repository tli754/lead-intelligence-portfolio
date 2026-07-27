"""The real `RobotsPolicyGateway` adapter.

Fetches `robots.txt` itself (via this module's own `PageFetcher`), parses
it with `app.modules.discovery.domain.robots_parser.parse_robots_txt`
(direct pure-function reuse — see contract resolution #3) and evaluates
it with `domain/robots_policy.py`'s genuinely-new matching logic. Caches
the parsed rule groups (and extracted crawl-delays) per host for the
lifetime of one gateway instance — a fresh instance is constructed per
crawl run by `application/website_crawl_service.py`'s caller, so this
avoids refetching `robots.txt` once per target within the same run.

A missing/unreachable `robots.txt` (404, timeout, connection error)
resolves to `outcome="unknown"` with the caller expected to record a
warning — this gateway itself never raises.
"""

import logging
from urllib.parse import urlsplit

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.exceptions import CrawlFetchError
from app.modules.crawling.domain.gateway import RobotsPolicyGateway
from app.modules.crawling.domain.page_fetcher import PageFetcher, PageFetchRequest
from app.modules.crawling.domain.robots_policy import (
    RobotsPolicyEvaluation,
    evaluate_robots_policy,
    extract_crawl_delays,
    matched_crawl_delay,
)
from app.modules.discovery.domain.models import RobotsRuleGroup
from app.modules.discovery.domain.robots_parser import parse_robots_txt

logger = logging.getLogger(__name__)

_CachedPolicy = tuple[list[RobotsRuleGroup], dict[str, float]]


class HttpRobotsPolicyGateway(RobotsPolicyGateway):
    def __init__(self, page_fetcher: PageFetcher, config: CrawlConfig | None = None) -> None:
        self._page_fetcher = page_fetcher
        self._config = config or CrawlConfig()
        self._cache: dict[str, _CachedPolicy] = {}

    async def get_policy(
        self, company_id: str, url: str, user_agent: str
    ) -> RobotsPolicyEvaluation:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"

        if origin not in self._cache:
            self._cache[origin] = await self._fetch_and_parse(origin)
        rule_groups, delays = self._cache[origin]

        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        crawl_delay = matched_crawl_delay(delays, user_agent=user_agent)
        return evaluate_robots_policy(
            rule_groups,
            path=path,
            user_agent=user_agent,
            max_crawl_delay_s=self._config.max_honored_crawl_delay_s,
            crawl_delay_s=crawl_delay,
        )

    async def _fetch_and_parse(self, origin: str) -> _CachedPolicy:
        robots_url = f"{origin}/robots.txt"
        try:
            result = await self._page_fetcher.fetch_page(
                PageFetchRequest(url=robots_url, expected_content_type="text/plain")
            )
        except CrawlFetchError as error:
            logger.info("robots.txt unavailable for %s: %s", robots_url, error)
            return [], {}

        if result.body is None or result.status_code >= 400:
            return [], {}

        text = result.body.decode("utf-8", errors="replace")
        try:
            parsed = parse_robots_txt(text)
        except Exception as error:  # a malformed robots.txt must not block the run
            logger.info("failed to parse robots.txt for %s: %s", robots_url, error)
            return [], {}

        return parsed.rule_groups, extract_crawl_delays(text)
