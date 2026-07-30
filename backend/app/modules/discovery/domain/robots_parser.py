"""Parses `robots.txt` for sitemap directives and raw rule groups.

Pure, line-based, stdlib-only. Deliberately does **not** implement
crawling-permission enforcement (matching a URL against `Disallow`
rules) — only captures the raw structure so a future crawler module can
do that matching itself, per the task's explicit scope.
"""

from app.modules.discovery.domain.models import RobotsPolicyResult, RobotsRuleGroup

_SITEMAP_DIRECTIVE = "sitemap:"
_USER_AGENT_DIRECTIVE = "user-agent:"
_DISALLOW_DIRECTIVE = "disallow:"
_ALLOW_DIRECTIVE = "allow:"
_KNOWN_DIRECTIVES = (
    _SITEMAP_DIRECTIVE,
    _USER_AGENT_DIRECTIVE,
    _DISALLOW_DIRECTIVE,
    _ALLOW_DIRECTIVE,
)


def parse_robots_txt(text: str) -> RobotsPolicyResult:
    """Parses robots.txt content already fetched by the caller.

    A missing/empty robots.txt is represented by the caller simply never
    calling this function (or calling it with `""`) — either way this
    returns an empty-but-successful result, never an error: a missing
    robots file is normal, not a failure.
    """
    sitemap_urls: list[str] = []
    warnings: list[str] = []
    rule_groups: list[RobotsRuleGroup] = []
    current_group: RobotsRuleGroup | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        lowered = line.lower()

        if lowered.startswith(_SITEMAP_DIRECTIVE):
            url = line[len("sitemap:") :].strip()
            if url:
                sitemap_urls.append(url)
            else:
                warnings.append(f"malformed Sitemap directive: {raw_line!r}")
            continue

        if lowered.startswith(_USER_AGENT_DIRECTIVE):
            agent = line[len("user-agent:") :].strip()
            if current_group is None or current_group.disallow or current_group.allow:
                current_group = RobotsRuleGroup()
                rule_groups.append(current_group)
            if agent:
                current_group.user_agents.append(agent)
            else:
                warnings.append(f"malformed User-agent directive: {raw_line!r}")
            continue

        if lowered.startswith(_DISALLOW_DIRECTIVE):
            if current_group is None:
                current_group = RobotsRuleGroup()
                rule_groups.append(current_group)
            current_group.disallow.append(line[len("disallow:") :].strip())
            continue

        if lowered.startswith(_ALLOW_DIRECTIVE):
            if current_group is None:
                current_group = RobotsRuleGroup()
                rule_groups.append(current_group)
            current_group.allow.append(line[len("allow:") :].strip())
            continue

        if not any(lowered.startswith(prefix) for prefix in _KNOWN_DIRECTIVES) and ":" in line:
            # An unrecognized but directive-shaped line (has a colon) —
            # a genuinely malformed/unknown directive, worth a warning.
            # A line with no colon at all is just noise (e.g. stray text)
            # and not worth warning about.
            warnings.append(f"unrecognized directive: {raw_line!r}")

    return RobotsPolicyResult(
        sitemap_urls=sitemap_urls, rule_groups=rule_groups, warnings=warnings, found=True
    )
