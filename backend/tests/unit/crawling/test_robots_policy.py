"""Unit tests for `domain/robots_policy.py` — pure, no I/O."""

from app.modules.crawling.domain.robots_policy import (
    evaluate_robots_policy,
    extract_crawl_delays,
    matched_crawl_delay,
)
from app.modules.discovery.domain.models import RobotsRuleGroup

USER_AGENT = "LeadIntelligenceCrawlBot"


def test_disallow_blocks() -> None:
    groups = [RobotsRuleGroup(user_agents=["*"], disallow=["/checkout"], allow=[])]

    result = evaluate_robots_policy(
        groups, path="/checkout", user_agent=USER_AGENT, max_crawl_delay_s=10.0
    )

    assert result.outcome == "disallowed"
    assert result.matched_rule == "Disallow: /checkout"
    assert result.source == "robots_txt"


def test_allowed_path() -> None:
    groups = [RobotsRuleGroup(user_agents=["*"], disallow=["/admin"], allow=[])]

    result = evaluate_robots_policy(
        groups, path="/about", user_agent=USER_AGENT, max_crawl_delay_s=10.0
    )

    assert result.outcome == "allowed"
    assert result.matched_rule is None


def test_no_matching_group_is_unknown() -> None:
    result = evaluate_robots_policy(
        [], path="/about", user_agent=USER_AGENT, max_crawl_delay_s=10.0
    )

    assert result.outcome == "unknown"
    assert result.source == "unknown_default"


def test_exact_user_agent_preferred_over_wildcard() -> None:
    groups = [
        RobotsRuleGroup(user_agents=["*"], disallow=[], allow=[]),
        RobotsRuleGroup(user_agents=[USER_AGENT], disallow=["/private"], allow=[]),
    ]

    result = evaluate_robots_policy(
        groups, path="/private", user_agent=USER_AGENT, max_crawl_delay_s=10.0
    )

    assert result.outcome == "disallowed"


def test_longest_matching_path_wins() -> None:
    groups = [
        RobotsRuleGroup(user_agents=["*"], disallow=["/products"], allow=["/products/public"])
    ]

    result = evaluate_robots_policy(
        groups, path="/products/public/item", user_agent=USER_AGENT, max_crawl_delay_s=10.0
    )

    assert result.outcome == "allowed"
    assert result.matched_rule == "Allow: /products/public"


def test_extreme_crawl_delay_capped() -> None:
    groups = [RobotsRuleGroup(user_agents=["*"], disallow=[], allow=[])]

    result = evaluate_robots_policy(
        groups,
        path="/",
        user_agent=USER_AGENT,
        max_crawl_delay_s=10.0,
        crawl_delay_s=300.0,
    )

    assert result.crawl_delay == 10.0


def test_crawl_delay_within_limit_is_not_altered() -> None:
    groups = [RobotsRuleGroup(user_agents=["*"], disallow=[], allow=[])]

    result = evaluate_robots_policy(
        groups,
        path="/",
        user_agent=USER_AGENT,
        max_crawl_delay_s=10.0,
        crawl_delay_s=3.0,
    )

    assert result.crawl_delay == 3.0


class TestExtractCrawlDelays:
    def test_extracts_per_agent_delay(self) -> None:
        text = "User-agent: *\nCrawl-delay: 5\nUser-agent: BadBot\nCrawl-delay: 60\n"

        delays = extract_crawl_delays(text)

        assert delays["*"] == 5.0
        assert delays["badbot"] == 60.0

    def test_ignores_invalid_values(self) -> None:
        text = "User-agent: *\nCrawl-delay: not-a-number\n"

        delays = extract_crawl_delays(text)

        assert delays == {}

    def test_matched_crawl_delay_prefers_exact_agent(self) -> None:
        delays = {"*": 5.0, "leadintelligencecrawlbot": 1.0}

        assert matched_crawl_delay(delays, user_agent="LeadIntelligenceCrawlBot") == 1.0
        assert matched_crawl_delay(delays, user_agent="OtherBot") == 5.0
