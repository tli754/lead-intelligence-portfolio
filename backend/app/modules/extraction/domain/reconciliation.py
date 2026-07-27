"""The deterministic reconciliation engine.

Groups candidates by `(company_id, field_path)`, merges agreeing
candidates, identifies conflicts, ranks candidates, selects the accepted
value(s), and produces a `FactRecord` (and a `FactConflict` where the
candidates genuinely disagree) — pure, deterministic, versioned
(`RECONCILIATION_RULES_VERSION`, imported from `reconciliation_rules.py`).

`existing_fact` (the company's currently-accepted fact for this field, if
any) is used only to decide whether the new outcome *supersedes* it — a
freshly-accepted value that differs from `existing_fact.normalized_value`
returns `existing_fact`'s own `selected_candidate_ids`/`fact_id` in
`superseded_candidate_ids`/via the outcome's `accepted_fact`, a signal the
application service uses to call `ExtractionRepository.mark_previous_facts_stale`
(brief section 18's "recent explicit evidence may override stale
evidence," realized this way rather than by re-deriving staleness inside
this pure function — staleness itself is `freshness_policy.py`'s concern,
tested standalone).
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.modules.extraction.domain.enums import FactSourceType, FactStatus, VerificationState
from app.modules.extraction.domain.field_catalogue import FieldDefinition
from app.modules.extraction.domain.models import (
    ConfidenceScore,
    FactCandidate,
    FactConflict,
    FactRecord,
)
from app.modules.extraction.domain.reconciliation_rules import (
    RULE_ARRAY_SET_UNION,
    RULE_BELOW_THRESHOLD_UNKNOWN,
    RULE_BOOLEAN_EXPLICIT_FALSE,
    RULE_BOOLEAN_POSITIVE_ONLY,
    RULE_EXACT_BEATS_ESTIMATE,
    RULE_EXACT_COUNTS_CONFLICT,
    RULE_HIGHEST_CONFIDENCE_SCALAR,
    RULE_JSON_LD_OVERRIDES_TITLE,
    RULE_MANUAL_OVERRIDES_AUTOMATED,
    RULE_STRONG_SOURCES_CONFLICT,
    RULE_STRUCTURED_ENTITY_MERGE,
    RULE_TIME_SERIES_APPENDED,
    MergeStrategy,
)

# Relative ranking of how authoritative a source type is, used to decide
# whether one group of agreeing candidates clearly outranks another (an
# override, e.g. JSON-LD beating a title-text inference) versus the two
# groups being genuine, unresolved peers (a conflict). Higher is stronger.
_SOURCE_PRIORITY: dict[FactSourceType, int] = {
    FactSourceType.MANUAL: 1000,
    FactSourceType.JSON_LD: 100,
    FactSourceType.OPEN_GRAPH: 90,
    FactSourceType.SITEMAP_SUMMARY: 85,
    FactSourceType.META_TAG: 80,
    FactSourceType.SCRIPT_MARKER: 70,
    FactSourceType.COOKIE_MARKER: 65,
    FactSourceType.HTML_ELEMENT: 60,
    FactSourceType.PAGE_METADATA: 60,
    FactSourceType.LINK: 55,
    FactSourceType.FORM: 50,
    FactSourceType.IMPORTED: 40,
    FactSourceType.DETERMINISTIC_INFERENCE: 20,
}

_PRIORITY_OVERRIDE_GAP = 20


class ReconciliationConfig(BaseModel):
    """Tunable knobs, never read from `os.environ` (matches every prior
    module's injectable-config pattern)."""

    priority_override_gap: int = _PRIORITY_OVERRIDE_GAP


class ReconciliationOutcome(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    accepted_fact: FactRecord | None = None
    conflict: FactConflict | None = None
    superseded_candidate_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)


def group_candidates(
    candidates: list[FactCandidate],
) -> dict[tuple[str, Any], list[FactCandidate]]:
    """Groups a flat candidate list by `(company_id, field_path)` — the
    unit reconciliation operates on (brief section 16's "group candidates
    by company and field path")."""
    groups: dict[tuple[str, Any], list[FactCandidate]] = defaultdict(list)
    for candidate in candidates:
        groups[(candidate.company_id, candidate.field_path)].append(candidate)
    return dict(groups)


def _normalize_key(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _eligible(candidates: list[FactCandidate], threshold: int) -> list[FactCandidate]:
    return [candidate for candidate in candidates if candidate.confidence >= threshold]


def _new_fact(
    *,
    candidates: list[FactCandidate],
    field_definition: FieldDefinition,
    value: Any,
    normalized_value: Any,
    confidence: ConfidenceScore,
    verification_state: VerificationState,
    status: FactStatus,
    selected_candidate_ids: list[str],
    conflicting_candidate_ids: list[str],
    rule_ids: list[str],
    source_count: int,
) -> FactRecord:
    now = datetime.now(UTC)
    observed_ats = [candidate.observed_at for candidate in candidates] or [now]
    extractor_versions = {
        candidate.extractor_id: candidate.extractor_version for candidate in candidates
    }
    fact_qualifiers: dict[str, Any] = {}
    for candidate in candidates:
        if candidate.candidate_id in selected_candidate_ids:
            for key in ("estimation_method", "sample_size", "exact"):
                if key in candidate.qualifiers:
                    fact_qualifiers[key] = candidate.qualifiers[key]
    return FactRecord(
        company_id=candidates[0].company_id,
        extraction_run_id=candidates[0].extraction_run_id,
        field_path=field_definition.field_path,
        value=value,
        normalized_value=normalized_value,
        value_type=field_definition.value_type,
        status=status,
        verification_state=verification_state,
        confidence=confidence,
        evidence_ids=[
            evidence_id
            for candidate in candidates
            if candidate.candidate_id in selected_candidate_ids
            for evidence_id in candidate.evidence_ids
        ],
        selected_candidate_ids=selected_candidate_ids,
        conflicting_candidate_ids=conflicting_candidate_ids,
        source_count=source_count,
        first_observed_at=min(observed_ats),
        last_observed_at=max(observed_ats),
        last_verified_at=now,
        extractor_versions=extractor_versions,
        reconciliation_rule_ids=rule_ids,
        qualifiers=fact_qualifiers,
        created_at=now,
        updated_at=now,
    )


def _unknown_outcome(rule_ids: list[str]) -> ReconciliationOutcome:
    return ReconciliationOutcome(accepted_fact=None, conflict=None, rule_ids=rule_ids)


def _supersession(existing_fact: FactRecord | None, new_normalized_value: Any) -> list[str]:
    if existing_fact is None:
        return []
    if _normalize_key(existing_fact.normalized_value) == _normalize_key(new_normalized_value):
        return []
    return list(existing_fact.selected_candidate_ids)


def _supersession_on_conflict(existing_fact: FactRecord | None) -> list[str]:
    """A previously-accepted fact is always superseded once its field
    becomes conflicting — there is no single new value to compare it
    against, but the old fact no longer reflects current consensus and
    must be marked stale rather than left silently accepted forever."""
    if existing_fact is None or existing_fact.status == FactStatus.CONFLICTING:
        return []
    return list(existing_fact.selected_candidate_ids)


def _reconcile_scalar(
    candidates: list[FactCandidate],
    *,
    field_definition: FieldDefinition,
    existing_fact: FactRecord | None,
    config: ReconciliationConfig,
) -> ReconciliationOutcome:
    manual_candidates = [c for c in candidates if c.source_type == FactSourceType.MANUAL]
    if manual_candidates:
        winner = max(manual_candidates, key=lambda c: c.confidence)
        fact = _new_fact(
            candidates=[winner],
            field_definition=field_definition,
            value=winner.value,
            normalized_value=winner.normalized_value,
            confidence=winner.confidence,
            verification_state=VerificationState.VERIFIED,
            status=FactStatus.ACCEPTED,
            selected_candidate_ids=[winner.candidate_id],
            conflicting_candidate_ids=[],
            rule_ids=[RULE_MANUAL_OVERRIDES_AUTOMATED],
            source_count=1,
        )
        return ReconciliationOutcome(
            accepted_fact=fact,
            superseded_candidate_ids=_supersession(existing_fact, winner.normalized_value),
            rule_ids=[RULE_MANUAL_OVERRIDES_AUTOMATED],
        )

    eligible = _eligible(candidates, field_definition.minimum_accepted_confidence)
    if not eligible:
        return _unknown_outcome([RULE_BELOW_THRESHOLD_UNKNOWN])

    value_groups: dict[Any, list[FactCandidate]] = defaultdict(list)
    for candidate in eligible:
        value_groups[_normalize_key(candidate.normalized_value)].append(candidate)

    if len(value_groups) == 1:
        (group,) = value_groups.values()
        best = max(group, key=lambda c: c.confidence)
        fact = _new_fact(
            candidates=group,
            field_definition=field_definition,
            value=best.value,
            normalized_value=best.normalized_value,
            confidence=max(c.confidence for c in group),
            verification_state=(
                VerificationState.VERIFIED
                if len(group) > 1
                else (
                    VerificationState.INFERRED
                    if best.source_type == FactSourceType.DETERMINISTIC_INFERENCE
                    else VerificationState.MEASURED
                )
            ),
            status=FactStatus.ACCEPTED,
            selected_candidate_ids=[c.candidate_id for c in group],
            conflicting_candidate_ids=[],
            rule_ids=[RULE_HIGHEST_CONFIDENCE_SCALAR],
            source_count=len(group),
        )
        return ReconciliationOutcome(
            accepted_fact=fact,
            superseded_candidate_ids=_supersession(existing_fact, best.normalized_value),
            rule_ids=[RULE_HIGHEST_CONFIDENCE_SCALAR],
        )

    # Multiple distinct values among eligible candidates — check for a
    # clear source-priority override (e.g. JSON-LD over a title inference)
    # before concluding this is a genuine, unresolved conflict.
    ranked_groups = sorted(
        value_groups.values(),
        key=lambda group: (
            max(_SOURCE_PRIORITY.get(c.source_type, 0) for c in group),
            max(c.confidence for c in group),
        ),
        reverse=True,
    )
    best_group, runner_up_group = ranked_groups[0], ranked_groups[1]
    best_priority = max(_SOURCE_PRIORITY.get(c.source_type, 0) for c in best_group)
    runner_up_priority = max(_SOURCE_PRIORITY.get(c.source_type, 0) for c in runner_up_group)

    if best_priority - runner_up_priority >= config.priority_override_gap:
        best = max(best_group, key=lambda c: c.confidence)
        fact = _new_fact(
            candidates=best_group,
            field_definition=field_definition,
            value=best.value,
            normalized_value=best.normalized_value,
            confidence=max(c.confidence for c in best_group),
            verification_state=VerificationState.VERIFIED,
            status=FactStatus.ACCEPTED,
            selected_candidate_ids=[c.candidate_id for c in best_group],
            conflicting_candidate_ids=[c.candidate_id for c in runner_up_group],
            rule_ids=[RULE_JSON_LD_OVERRIDES_TITLE],
            source_count=len(best_group),
        )
        return ReconciliationOutcome(
            accepted_fact=fact,
            superseded_candidate_ids=_supersession(existing_fact, best.normalized_value),
            rule_ids=[RULE_JSON_LD_OVERRIDES_TITLE],
        )

    # Genuine, unresolved conflict between comparably-authoritative sources
    # — never silently resolved by first-seen order.
    all_eligible_ids = [c.candidate_id for c in eligible]
    conflict = FactConflict(
        company_id=candidates[0].company_id,
        extraction_run_id=candidates[0].extraction_run_id,
        field_path=field_definition.field_path,
        candidate_ids=all_eligible_ids,
        selected_candidate_id=None,
        conflict_type="scalar_value_conflict",
        resolution=None,
        rule_ids=[RULE_STRONG_SOURCES_CONFLICT],
        created_at=datetime.now(UTC),
    )
    fact = _new_fact(
        candidates=eligible,
        field_definition=field_definition,
        value=None,
        normalized_value=None,
        confidence=max(c.confidence for c in eligible),
        verification_state=VerificationState.CONFLICTING,
        status=FactStatus.CONFLICTING,
        selected_candidate_ids=[],
        conflicting_candidate_ids=all_eligible_ids,
        rule_ids=[RULE_STRONG_SOURCES_CONFLICT],
        source_count=len(eligible),
    )
    return ReconciliationOutcome(
        accepted_fact=fact,
        conflict=conflict,
        superseded_candidate_ids=_supersession_on_conflict(existing_fact),
        rule_ids=[RULE_STRONG_SOURCES_CONFLICT],
    )


def _reconcile_boolean(
    candidates: list[FactCandidate],
    *,
    field_definition: FieldDefinition,
    existing_fact: FactRecord | None,
    explicit_false_allowed: bool,
) -> ReconciliationOutcome:
    eligible = _eligible(candidates, field_definition.minimum_accepted_confidence)
    true_candidates = [c for c in eligible if c.value is True]
    false_candidates = [c for c in eligible if c.value is False] if explicit_false_allowed else []

    if true_candidates and false_candidates:
        all_ids = [c.candidate_id for c in true_candidates + false_candidates]
        conflict = FactConflict(
            company_id=candidates[0].company_id,
            extraction_run_id=candidates[0].extraction_run_id,
            field_path=field_definition.field_path,
            candidate_ids=all_ids,
            conflict_type="boolean_value_conflict",
            rule_ids=[RULE_STRONG_SOURCES_CONFLICT],
            created_at=datetime.now(UTC),
        )
        fact = _new_fact(
            candidates=eligible,
            field_definition=field_definition,
            value=None,
            normalized_value=None,
            confidence=max(c.confidence for c in eligible),
            verification_state=VerificationState.CONFLICTING,
            status=FactStatus.CONFLICTING,
            selected_candidate_ids=[],
            conflicting_candidate_ids=all_ids,
            rule_ids=[RULE_STRONG_SOURCES_CONFLICT],
            source_count=len(eligible),
        )
        return ReconciliationOutcome(
            accepted_fact=fact,
            conflict=conflict,
            superseded_candidate_ids=_supersession_on_conflict(existing_fact),
            rule_ids=[RULE_STRONG_SOURCES_CONFLICT],
        )

    if true_candidates:
        rule = RULE_BOOLEAN_POSITIVE_ONLY
        fact = _new_fact(
            candidates=true_candidates,
            field_definition=field_definition,
            value=True,
            normalized_value=True,
            confidence=max(c.confidence for c in true_candidates),
            verification_state=VerificationState.VERIFIED,
            status=FactStatus.ACCEPTED,
            selected_candidate_ids=[c.candidate_id for c in true_candidates],
            conflicting_candidate_ids=[],
            rule_ids=[rule],
            source_count=len(true_candidates),
        )
        return ReconciliationOutcome(
            accepted_fact=fact,
            superseded_candidate_ids=_supersession(existing_fact, True),
            rule_ids=[rule],
        )

    if false_candidates:
        fact = _new_fact(
            candidates=false_candidates,
            field_definition=field_definition,
            value=False,
            normalized_value=False,
            confidence=max(c.confidence for c in false_candidates),
            verification_state=VerificationState.VERIFIED,
            status=FactStatus.ACCEPTED,
            selected_candidate_ids=[c.candidate_id for c in false_candidates],
            conflicting_candidate_ids=[],
            rule_ids=[RULE_BOOLEAN_EXPLICIT_FALSE],
            source_count=len(false_candidates),
        )
        return ReconciliationOutcome(
            accepted_fact=fact,
            superseded_candidate_ids=_supersession(existing_fact, False),
            rule_ids=[RULE_BOOLEAN_EXPLICIT_FALSE],
        )

    return _unknown_outcome([RULE_BELOW_THRESHOLD_UNKNOWN])


def _dedup_key(candidate: FactCandidate) -> Any:
    explicit_key = candidate.qualifiers.get("dedup_key")
    if explicit_key is not None:
        return _normalize_key(explicit_key)
    return _normalize_key(candidate.normalized_value)


def _reconcile_array(
    candidates: list[FactCandidate],
    *,
    field_definition: FieldDefinition,
    existing_fact: FactRecord | None,
    rule_id: str,
) -> ReconciliationOutcome:
    eligible = _eligible(candidates, field_definition.minimum_accepted_confidence)
    if not eligible:
        return _unknown_outcome([RULE_BELOW_THRESHOLD_UNKNOWN])

    items_by_key: dict[Any, list[FactCandidate]] = defaultdict(list)
    for candidate in eligible:
        items_by_key[_dedup_key(candidate)].append(candidate)

    merged_items: list[dict[str, Any]] = []
    selected_candidate_ids: list[str] = []
    for group in items_by_key.values():
        best = max(group, key=lambda c: c.confidence)
        evidence_ids = [eid for c in group for eid in c.evidence_ids]
        merged_items.append(
            {
                "value": best.normalized_value,
                "confidence": max(c.confidence for c in group),
                "evidence_ids": evidence_ids,
                "source_count": len(group),
                "sort_key": min(c.qualifiers.get("sort_key", 0) for c in group),
            }
        )
        selected_candidate_ids.extend(c.candidate_id for c in group)

    # Priority-ordered fields (e.g. `organisation.recommended_contact_candidates`)
    # attach a `sort_key` qualifier per candidate — stable-sorted here so
    # reconciliation never silently reorders an extractor's intended
    # priority, and fields that never set it keep insertion order (all
    # default to `0`).
    merged_items.sort(key=lambda item: item["sort_key"])

    raw_values = [item["value"] for item in merged_items]
    fact = _new_fact(
        candidates=eligible,
        field_definition=field_definition,
        value=raw_values,
        normalized_value=merged_items,
        confidence=max(item["confidence"] for item in merged_items),
        verification_state=VerificationState.VERIFIED,
        status=FactStatus.ACCEPTED,
        selected_candidate_ids=selected_candidate_ids,
        conflicting_candidate_ids=[],
        rule_ids=[rule_id],
        source_count=len(eligible),
    )
    return ReconciliationOutcome(accepted_fact=fact, rule_ids=[rule_id])


def _is_exact(candidate: FactCandidate) -> bool:
    method = candidate.qualifiers.get("estimation_method")
    return method is None or method == "exact" or candidate.qualifiers.get("exact") is True


def _reconcile_numeric(
    candidates: list[FactCandidate],
    *,
    field_definition: FieldDefinition,
    existing_fact: FactRecord | None,
) -> ReconciliationOutcome:
    eligible = _eligible(candidates, field_definition.minimum_accepted_confidence)
    if not eligible:
        return _unknown_outcome([RULE_BELOW_THRESHOLD_UNKNOWN])

    exact_candidates = [c for c in eligible if _is_exact(c)]
    if exact_candidates:
        distinct_values = {_normalize_key(c.normalized_value) for c in exact_candidates}
        if len(distinct_values) == 1:
            best = max(exact_candidates, key=lambda c: c.confidence)
            fact = _new_fact(
                candidates=exact_candidates,
                field_definition=field_definition,
                value=best.value,
                normalized_value=best.normalized_value,
                confidence=max(c.confidence for c in exact_candidates),
                verification_state=VerificationState.MEASURED,
                status=FactStatus.ACCEPTED,
                selected_candidate_ids=[c.candidate_id for c in exact_candidates],
                conflicting_candidate_ids=[],
                rule_ids=[RULE_EXACT_BEATS_ESTIMATE],
                source_count=len(exact_candidates),
            )
            return ReconciliationOutcome(
                accepted_fact=fact,
                superseded_candidate_ids=_supersession(existing_fact, best.normalized_value),
                rule_ids=[RULE_EXACT_BEATS_ESTIMATE],
            )

        all_ids = [c.candidate_id for c in exact_candidates]
        conflict = FactConflict(
            company_id=candidates[0].company_id,
            extraction_run_id=candidates[0].extraction_run_id,
            field_path=field_definition.field_path,
            candidate_ids=all_ids,
            conflict_type="competing_exact_counts",
            rule_ids=[RULE_EXACT_COUNTS_CONFLICT],
            created_at=datetime.now(UTC),
        )
        fact = _new_fact(
            candidates=exact_candidates,
            field_definition=field_definition,
            value=None,
            normalized_value=None,
            confidence=max(c.confidence for c in exact_candidates),
            verification_state=VerificationState.CONFLICTING,
            status=FactStatus.CONFLICTING,
            selected_candidate_ids=[],
            conflicting_candidate_ids=all_ids,
            rule_ids=[RULE_EXACT_COUNTS_CONFLICT],
            source_count=len(exact_candidates),
        )
        return ReconciliationOutcome(
            accepted_fact=fact,
            conflict=conflict,
            superseded_candidate_ids=_supersession_on_conflict(existing_fact),
            rule_ids=[RULE_EXACT_COUNTS_CONFLICT],
        )

    best = max(eligible, key=lambda c: c.confidence)
    fact = _new_fact(
        candidates=eligible,
        field_definition=field_definition,
        value=best.value,
        normalized_value=best.normalized_value,
        confidence=best.confidence,
        verification_state=VerificationState.INFERRED,
        status=FactStatus.ACCEPTED,
        selected_candidate_ids=[best.candidate_id],
        conflicting_candidate_ids=[],
        rule_ids=[RULE_HIGHEST_CONFIDENCE_SCALAR],
        source_count=1,
    )
    return ReconciliationOutcome(
        accepted_fact=fact,
        superseded_candidate_ids=_supersession(existing_fact, best.normalized_value),
        rule_ids=[RULE_HIGHEST_CONFIDENCE_SCALAR],
    )


def reconcile_candidates(
    candidates: list[FactCandidate],
    *,
    field_definition: FieldDefinition,
    existing_fact: FactRecord | None = None,
    config: ReconciliationConfig | None = None,
) -> ReconciliationOutcome:
    """Reconciles every candidate for **one** `(company_id, field_path)`
    group — call `group_candidates` first to split a flat candidate list.
    Returns `accepted_fact=None` (unknown) when nothing passes threshold,
    never a guessed value; never emits `False` for a boolean field without
    an explicit negative-evidence candidate."""
    config = config or ReconciliationConfig()
    if not candidates:
        return _unknown_outcome([RULE_BELOW_THRESHOLD_UNKNOWN])

    strategy = field_definition.merge_strategy
    if strategy in (MergeStrategy.SCALAR_PREFERRED, MergeStrategy.SCALAR_CONFLICT_PRESERVING):
        return _reconcile_scalar(
            candidates,
            field_definition=field_definition,
            existing_fact=existing_fact,
            config=config,
        )
    if strategy == MergeStrategy.BOOLEAN_POSITIVE_ONLY:
        return _reconcile_boolean(
            candidates,
            field_definition=field_definition,
            existing_fact=existing_fact,
            explicit_false_allowed=False,
        )
    if strategy == MergeStrategy.BOOLEAN_EXPLICIT:
        return _reconcile_boolean(
            candidates,
            field_definition=field_definition,
            existing_fact=existing_fact,
            explicit_false_allowed=True,
        )
    if strategy == MergeStrategy.SET_UNION:
        return _reconcile_array(
            candidates,
            field_definition=field_definition,
            existing_fact=existing_fact,
            rule_id=RULE_ARRAY_SET_UNION,
        )
    if strategy == MergeStrategy.STRUCTURED_ENTITY_MERGE:
        return _reconcile_array(
            candidates,
            field_definition=field_definition,
            existing_fact=existing_fact,
            rule_id=RULE_STRUCTURED_ENTITY_MERGE,
        )
    if strategy == MergeStrategy.TIME_SERIES:
        return _reconcile_array(
            candidates,
            field_definition=field_definition,
            existing_fact=existing_fact,
            rule_id=RULE_TIME_SERIES_APPENDED,
        )
    if strategy == MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE:
        return _reconcile_numeric(
            candidates, field_definition=field_definition, existing_fact=existing_fact
        )

    raise ValueError(f"unsupported merge strategy: {strategy!r}")
