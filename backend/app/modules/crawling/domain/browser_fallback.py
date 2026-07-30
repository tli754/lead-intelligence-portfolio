"""Deterministic browser-fallback detection.

Operates only on already-cleaned HTML, already-extracted text, and an
optional challenge classification — never fetches or renders anything
itself. Every rule has a stable id and a fixed confidence; when multiple
rules match, the highest-confidence match wins. Ties are broken by this
module's own fixed rule-priority order (`_RULE_PRIORITY_ORDER`), so the
result is always deterministic even when several rules fire together.

Rule ids implemented: `browser:manual`, `browser:challenge-page`,
`browser:nextjs-shell`, `browser:react-shell`, `browser:vue-shell`,
`browser:empty-shell`, `browser:script-heavy`. The contract's illustrative
`browser:explicit-js-required` rule id is not implemented as a separate
detector — this function only ever sees cleaned HTML (its own
`<noscript>` boilerplate is deliberately stripped entirely by
`domain/html_cleaner.py`), so an explicit "you need JavaScript" notice
would never survive to be matched here; the same underlying pages are
still caught by `browser:script-heavy`/`browser:empty-shell` instead.
This is a documented, deliberate scope reduction, not a silent omission.
"""

from pydantic import BaseModel

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.enums import BrowserFallbackReason
from app.modules.crawling.domain.html_validator import BlockedPageClassification


class BrowserFallbackDecision(BaseModel):
    browser_required: bool
    reason: BrowserFallbackReason | None
    confidence: int
    rule_ids: list[str]


class _RuleMatch(BaseModel):
    rule_id: str
    reason: BrowserFallbackReason
    confidence: int


# Tie-break order when two rules report the same confidence — earlier
# entries win. Kept separate from confidence values so ties are resolved
# by an explicit, documented order rather than dict/set iteration order.
_RULE_PRIORITY_ORDER: tuple[str, ...] = (
    "browser:manual",
    "browser:challenge-page",
    "browser:nextjs-shell",
    "browser:react-shell",
    "browser:vue-shell",
    "browser:empty-shell",
    "browser:script-heavy",
)


def _rule_sort_key(match: _RuleMatch) -> tuple[int, int]:
    priority_index = (
        _RULE_PRIORITY_ORDER.index(match.rule_id)
        if match.rule_id in _RULE_PRIORITY_ORDER
        else len(_RULE_PRIORITY_ORDER)
    )
    return (-match.confidence, priority_index)


def detect_browser_fallback(
    cleaned_html: str,
    extracted_text: str,
    challenge_classification: BlockedPageClassification | None,
    *,
    manual_override: bool,
    config: CrawlConfig,
) -> BrowserFallbackDecision:
    text_length = len(extracted_text.strip())
    matches: list[_RuleMatch] = []

    if manual_override:
        matches.append(
            _RuleMatch(
                rule_id="browser:manual",
                reason=BrowserFallbackReason.MANUALLY_REQUESTED,
                confidence=100,
            )
        )

    if challenge_classification is not None:
        matches.append(
            _RuleMatch(
                rule_id="browser:challenge-page",
                reason=BrowserFallbackReason.CHALLENGE_PAGE,
                confidence=95,
            )
        )

    is_shell_candidate = text_length <= config.browser_fallback_shell_max_text_length

    if is_shell_candidate and ("__NEXT_DATA__" in cleaned_html or 'id="__next"' in cleaned_html):
        matches.append(
            _RuleMatch(
                rule_id="browser:nextjs-shell",
                reason=BrowserFallbackReason.CLIENT_RENDERED_MARKER,
                confidence=90,
            )
        )

    if is_shell_candidate and "data-reactroot" in cleaned_html:
        matches.append(
            _RuleMatch(
                rule_id="browser:react-shell",
                reason=BrowserFallbackReason.CLIENT_RENDERED_MARKER,
                confidence=88,
            )
        )

    if is_shell_candidate and "v-cloak" in cleaned_html:
        matches.append(
            _RuleMatch(
                rule_id="browser:vue-shell",
                reason=BrowserFallbackReason.CLIENT_RENDERED_MARKER,
                confidence=86,
            )
        )

    if text_length == 0 and ('id="root"' in cleaned_html or 'id="app"' in cleaned_html):
        matches.append(
            _RuleMatch(
                rule_id="browser:empty-shell",
                reason=BrowserFallbackReason.EMPTY_HTML,
                confidence=80,
            )
        )

    script_tag_count = cleaned_html.count("<script")
    if (
        script_tag_count >= config.browser_fallback_script_heavy_min_scripts
        and text_length <= config.browser_fallback_script_heavy_max_text_length
    ):
        matches.append(
            _RuleMatch(
                rule_id="browser:script-heavy",
                reason=BrowserFallbackReason.INSUFFICIENT_TEXT,
                confidence=60,
            )
        )

    if not matches:
        return BrowserFallbackDecision(
            browser_required=False, reason=None, confidence=0, rule_ids=[]
        )

    matches.sort(key=_rule_sort_key)
    winner = matches[0]
    return BrowserFallbackDecision(
        browser_required=True,
        reason=winner.reason,
        confidence=winner.confidence,
        rule_ids=[match.rule_id for match in matches],
    )
