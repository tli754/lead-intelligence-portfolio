"""Same-domain / same-registrable-domain comparisons.

Pure string logic — no DNS lookups here (per the task: "do not fetch DNS
in domain logic"). Operates on already-normalized hostnames.
"""

# A short, hand-maintained list of common two-label public suffixes
# ("compound TLDs") — NOT a full Public Suffix List implementation (that
# would require a new dependency, out of scope for this module; see the
# execution-plan doc's "known limitations"). Registrable-domain results
# for anything outside this list fall back to a plain last-two-labels
# heuristic, which is wrong for many real compound suffixes.
_COMPOUND_SUFFIXES = frozenset(
    {
        "co.nz",
        "co.uk",
        "org.uk",
        "com.au",
        "co.za",
        "com.br",
        "co.jp",
        "or.jp",
        "ne.jp",
        "com.cn",
        "co.in",
        "co.id",
        "com.mx",
        "co.il",
        "com.sg",
        "com.hk",
        "co.kr",
        "com.tw",
    }
)


def is_same_domain(host_a: str | None, host_b: str | None) -> bool:
    """Exact hostname match (case-insensitive)."""
    if not host_a or not host_b:
        return False
    return host_a.lower() == host_b.lower()


def registrable_domain(hostname: str | None) -> str | None:
    """Best-effort eTLD+1 for `hostname` — a heuristic, not a full PSL
    implementation. See the module docstring's `_COMPOUND_SUFFIXES` note."""
    if not hostname:
        return None
    labels = hostname.lower().split(".")
    if len(labels) < 2:
        return hostname.lower()

    last_two = ".".join(labels[-2:])
    if last_two in _COMPOUND_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def is_same_registrable_domain(host_a: str | None, host_b: str | None) -> bool:
    domain_a = registrable_domain(host_a)
    domain_b = registrable_domain(host_b)
    if domain_a is None or domain_b is None:
        return False
    return domain_a == domain_b
