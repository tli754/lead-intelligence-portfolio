"""Merge-strategy vocabulary and per-field reconciliation rule identifiers.

Kept separate from `domain/reconciliation.py` (the engine that actually
*applies* these strategies) so that `domain/field_catalogue.py` — built
first, per the contract's suggested implementation order — can declare
each `FieldDefinition.merge_strategy` without importing the (much later)
reconciliation engine itself. This module has no dependency on
`field_catalogue.py`, so there is no import cycle.
"""

from enum import StrEnum

RECONCILIATION_RULES_VERSION = "v1"


class MergeStrategy(StrEnum):
    """How reconciliation combines multiple `FactCandidate`s for one field.

    Exactly brief section 16's list.
    """

    SCALAR_PREFERRED = "scalar_preferred"
    SCALAR_CONFLICT_PRESERVING = "scalar_conflict_preserving"
    BOOLEAN_POSITIVE_ONLY = "boolean_positive_only"
    BOOLEAN_EXPLICIT = "boolean_explicit"
    SET_UNION = "set_union"
    STRUCTURED_ENTITY_MERGE = "structured_entity_merge"
    NUMERIC_EXACT_OR_ESTIMATE = "numeric_exact_or_estimate"
    TIME_SERIES = "time_series"


# --- Rule IDs -------------------------------------------------------------
#
# Every reconciliation decision records which rule(s) fired
# (`FactRecord.reconciliation_rule_ids`, `FactConflict.rule_ids`) so a
# decision is always auditable, never a bare "trust me." Centralized here,
# versioned as one block via `RECONCILIATION_RULES_VERSION` above.

RULE_MANUAL_OVERRIDES_AUTOMATED = "reconciliation.manual_overrides_automated"
RULE_JSON_LD_OVERRIDES_TITLE = "reconciliation.json_ld_overrides_title_inference"
RULE_STRUCTURED_DATA_OVERRIDES_FOOTER = "reconciliation.structured_data_overrides_footer_count"
RULE_RECENT_OVERRIDES_STALE = "reconciliation.recent_explicit_overrides_stale"
RULE_STRONG_SOURCES_CONFLICT = "reconciliation.conflicting_strong_sources_preserved"
RULE_HIGHEST_CONFIDENCE_SCALAR = "reconciliation.highest_confidence_scalar_selected"
RULE_ARRAY_SET_UNION = "reconciliation.array_set_union_deduplicated"
RULE_BOOLEAN_POSITIVE_ONLY = "reconciliation.boolean_true_or_unknown_only"
RULE_BOOLEAN_EXPLICIT_FALSE = "reconciliation.boolean_false_requires_explicit_evidence"
RULE_BELOW_THRESHOLD_UNKNOWN = "reconciliation.below_threshold_remains_unknown"
RULE_EXACT_BEATS_ESTIMATE = "reconciliation.exact_value_beats_estimate"
RULE_EXACT_COUNTS_CONFLICT = "reconciliation.competing_exact_counts_conflict"
RULE_STRUCTURED_ENTITY_MERGE = "reconciliation.structured_entities_merged_deduplicated"
RULE_TIME_SERIES_APPENDED = "reconciliation.time_series_signal_appended"
