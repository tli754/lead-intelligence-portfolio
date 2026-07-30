"""Robots-permission evaluation — genuinely new logic owned by this module.

`app.modules.discovery.domain.robots_parser.parse_robots_txt` only ever
splits `robots.txt` into raw `RobotsRuleGroup`s and `Sitemap:` lines — it
explicitly does no matching/enforcement (see its own module docstring).
This file builds the matching/evaluation logic that reuses those parsed
`RobotsRuleGroup`s (imported directly from discovery, not duplicated —
per this contract's resolution #3) without reimplementing discovery's own
line-splitting.

**Why `crawl_delay_s` is a separate input, not read off `RobotsRuleGroup`:**
`RobotsRuleGroup` (reused as-is from discovery) has no `Crawl-delay`
field — discovery's parser never recognized that directive (it only
handles `Sitemap:`/`User-agent:`/`Disallow:`/`Allow:`). Extracting
`Crawl-delay` is itself part of the "genuinely new" logic this module
owns (see `extract_crawl_delays`, below) — its caller
(`infrastructure/http_robots_policy_gateway.py`) extracts it separately
from the same raw text and passes the matched value in here, rather than
this function re-deriving it from a field that doesn't exist on the
reused type.
"""

from typing import Literal

from pydantic import BaseModel

from app.modules.discovery.domain.models import RobotsRuleGroup

Outcome = Literal["allowed", "disallowed", "unknown"]
Source = Literal["robots_txt", "unknown_default"]

_CRAWL_DELAY_DIRECTIVE = "crawl-delay:"
_USER_AGENT_DIRECTIVE = "user-agent:"


class RobotsPolicyEvaluation(BaseModel):
    outcome: Outcome
    crawl_delay: float | None = None
    matched_rule: str | None = None
    source: Source


class _MatchedRule(BaseModel):
    kind: Literal["allow", "disallow"]
    pattern: str
    raw: str


def _matches(pattern: str, path: str) -> bool:
    # Basic robots.txt prefix matching — no `*`/`$` wildcard support,
    # matching the level of sophistication `parse_robots_txt` itself
    # already parses (plain literal rule strings).
    if pattern == "":
        # An empty Disallow/Allow value means "matches nothing" (the
        # conventional "allow everything" idiom for an empty Disallow).
        return False
    return path.startswith(pattern)


def _best_matching_groups(
    rule_groups: list[RobotsRuleGroup], *, user_agent: str
) -> list[RobotsRuleGroup]:
    """Selects every group whose `User-agent` line exactly matches
    `user_agent` (case-insensitive); falls back to every `*` group if no
    exact match exists. Multiple groups sharing the same applicable
    user-agent token are merged (their rules are evaluated together)."""
    lowered_agent = user_agent.lower()

    exact_matches = [
        group
        for group in rule_groups
        if any(agent.lower() == lowered_agent for agent in group.user_agents)
    ]
    if exact_matches:
        return exact_matches

    wildcard_matches = [group for group in rule_groups if "*" in group.user_agents]
    return wildcard_matches


def evaluate_robots_policy(
    rule_groups: list[RobotsRuleGroup],
    *,
    path: str,
    user_agent: str,
    max_crawl_delay_s: float,
    crawl_delay_s: float | None = None,
) -> RobotsPolicyEvaluation:
    """Evaluates whether `path` may be fetched under `user_agent`.

    Selects the best-matching `User-agent` group (exact match preferred
    over `*`); applies longest-matching-path precedence between
    `Allow`/`Disallow` (ties broken in `Allow`'s favor, the standard
    robots.txt convention); returns `crawl_delay` (already matched by the
    caller, see module docstring) capped at `max_crawl_delay_s`.
    """
    matching_groups = _best_matching_groups(rule_groups, user_agent=user_agent)
    if not matching_groups:
        return RobotsPolicyEvaluation(outcome="unknown", source="unknown_default")

    candidates: list[_MatchedRule] = []
    for group in matching_groups:
        for pattern in group.disallow:
            if _matches(pattern, path):
                candidates.append(
                    _MatchedRule(kind="disallow", pattern=pattern, raw=f"Disallow: {pattern}")
                )
        for pattern in group.allow:
            if _matches(pattern, path):
                candidates.append(
                    _MatchedRule(kind="allow", pattern=pattern, raw=f"Allow: {pattern}")
                )

    capped_delay = min(crawl_delay_s, max_crawl_delay_s) if crawl_delay_s is not None else None

    if not candidates:
        return RobotsPolicyEvaluation(
            outcome="allowed", crawl_delay=capped_delay, source="robots_txt"
        )

    # Longest matching pattern wins; ties resolved in `allow`'s favor.
    winner = max(candidates, key=lambda rule: (len(rule.pattern), rule.kind == "allow"))

    outcome: Outcome = "allowed" if winner.kind == "allow" else "disallowed"
    return RobotsPolicyEvaluation(
        outcome=outcome, crawl_delay=capped_delay, matched_rule=winner.raw, source="robots_txt"
    )


def extract_crawl_delays(text: str) -> dict[str, float]:
    """Extracts `Crawl-delay` values per `User-agent` token from raw
    `robots.txt` text.

    A small, standalone pass over the same text `parse_robots_txt`
    already splits into rule groups — this doesn't reimplement that
    line-splitting; it only adds the one directive discovery's parser
    never recognized. Keyed by lowercased user-agent token (`"*"` for the
    wildcard group). An invalid (non-numeric) value is ignored.
    """
    delays: dict[str, float] = {}
    current_agents: list[str] = []
    group_open = False

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        lowered = line.lower()

        if lowered.startswith(_USER_AGENT_DIRECTIVE):
            agent = line[len("user-agent:") :].strip()
            if not agent:
                continue
            if not group_open:
                current_agents = []
            current_agents.append(agent.lower())
            group_open = True
            continue

        if lowered.startswith(_CRAWL_DELAY_DIRECTIVE):
            group_open = False
            value = line[len("crawl-delay:") :].strip()
            try:
                delay = float(value)
            except ValueError:
                continue
            for agent in current_agents:
                delays[agent] = delay
            continue

        group_open = False

    return delays


def matched_crawl_delay(delays: dict[str, float], *, user_agent: str) -> float | None:
    """Looks up the crawl-delay applicable to `user_agent`, preferring an
    exact match over the `*` wildcard — the same preference order used
    for rule-group matching above."""
    lowered = user_agent.lower()
    if lowered in delays:
        return delays[lowered]
    return delays.get("*")
