"""Unit tests for `domain/browser_fallback.py` — pure, no I/O."""

from pathlib import Path

from app.modules.crawling.domain.browser_fallback import detect_browser_fallback
from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.html_cleaner import clean_html
from app.modules.crawling.domain.html_validator import classify_blocked_or_challenge
from app.modules.crawling.domain.text_extractor import extract_text

FIXTURES_DIR = Path(__file__).resolve().parents[3].parent / "fixtures" / "crawling"


def _decide(name: str, *, manual_override: bool = False):
    raw = (FIXTURES_DIR / name).read_text(encoding="utf-8")
    cleaned = clean_html(raw)
    text = extract_text(cleaned.html)
    classification = classify_blocked_or_challenge(raw)
    return detect_browser_fallback(
        cleaned.html,
        text.text,
        classification,
        manual_override=manual_override,
        config=CrawlConfig(),
    )


class TestNormalServerRenderedPage:
    def test_homepage_does_not_require_browser(self) -> None:
        decision = _decide("page-homepage.html")
        assert decision.browser_required is False
        assert decision.reason is None
        assert decision.rule_ids == []


class TestEmptyAppShell:
    def test_empty_shell_requires_browser(self) -> None:
        decision = _decide("page-empty-shell.html")
        assert decision.browser_required is True
        assert "browser:empty-shell" in decision.rule_ids


class TestReactShell:
    def test_react_shell_requires_browser(self) -> None:
        decision = _decide("page-react-shell.html")
        assert decision.browser_required is True
        assert decision.reason is not None
        assert decision.reason.value == "client_rendered_marker"
        assert "browser:react-shell" in decision.rule_ids


class TestVueShell:
    def test_vue_shell_requires_browser(self) -> None:
        decision = _decide("page-vue-shell.html")
        assert decision.browser_required is True
        assert "browser:vue-shell" in decision.rule_ids


class TestNextShell:
    def test_nextjs_shell_requires_browser(self) -> None:
        decision = _decide("page-next-shell.html")
        assert decision.browser_required is True
        assert "browser:nextjs-shell" in decision.rule_ids


class TestHighScriptToTextRatio:
    def test_heavy_scripts_page_requires_browser(self) -> None:
        decision = _decide("page-heavy-scripts.html")
        assert decision.browser_required is True
        assert "browser:script-heavy" in decision.rule_ids


class TestManualBrowserRequirement:
    def test_manual_override_forces_browser_required(self) -> None:
        decision = _decide("page-homepage.html", manual_override=True)
        assert decision.browser_required is True
        assert decision.reason is not None
        assert decision.reason.value == "manually_requested"
        assert decision.confidence == 100


class TestChallengePage:
    def test_challenge_page_requires_browser(self) -> None:
        decision = _decide("page-cloudflare-challenge.html")
        assert decision.browser_required is True
        assert "browser:challenge-page" in decision.rule_ids


class TestDeterministicRuleIds:
    def test_rerunning_yields_identical_rule_ids(self) -> None:
        first = _decide("page-react-shell.html")
        second = _decide("page-react-shell.html")
        assert first.rule_ids == second.rule_ids
        assert first.reason == second.reason
        assert first.confidence == second.confidence
