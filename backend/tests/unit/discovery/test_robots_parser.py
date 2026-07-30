from pathlib import Path

from app.modules.discovery.domain.robots_parser import parse_robots_txt

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "discovery"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


class TestParseRobotsTxt:
    def test_one_sitemap(self) -> None:
        result = parse_robots_txt(_load("robots-basic.txt"))
        assert result.sitemap_urls == ["https://summitoutfitters.example.com/sitemap.xml"]
        assert result.found is True

    def test_multiple_sitemaps_mixed_case_directive(self) -> None:
        result = parse_robots_txt(_load("robots-multiple-sitemaps.txt"))
        assert result.sitemap_urls == [
            "https://summitoutfitters.example.com/sitemap-index.xml",
            "https://summitoutfitters.example.com/sitemap-pages.xml",
            "https://summitoutfitters.example.com/sitemap-products.xml",
        ]

    def test_captures_rule_groups(self) -> None:
        result = parse_robots_txt(_load("robots-multiple-sitemaps.txt"))
        assert len(result.rule_groups) == 2
        assert result.rule_groups[0].user_agents == ["*"]
        assert "/cart" in result.rule_groups[0].disallow
        assert result.rule_groups[1].user_agents == ["BadBot"]

    def test_missing_robots_is_not_a_failure(self) -> None:
        result = parse_robots_txt("")
        assert result.sitemap_urls == []
        assert result.warnings == []
        assert result.found is True

    def test_malformed_sitemap_directive_produces_a_warning(self) -> None:
        result = parse_robots_txt("Sitemap:\n")
        assert result.sitemap_urls == []
        assert len(result.warnings) == 1
        assert "malformed Sitemap directive" in result.warnings[0]

    def test_comments_are_ignored(self) -> None:
        result = parse_robots_txt("# this is a comment\nSitemap: https://example.com/sitemap.xml\n")
        assert result.sitemap_urls == ["https://example.com/sitemap.xml"]
