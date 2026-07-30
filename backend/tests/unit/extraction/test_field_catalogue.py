"""Unit tests for the field-path catalogue (AC-01, AC-02)."""

from app.modules.extraction.domain.field_catalogue import (
    FIELD_CATALOGUE,
    FIELD_CATALOGUE_VERSION,
    FieldCardinality,
    FieldDefinition,
    FieldPath,
    FieldValueType,
)
from app.modules.extraction.domain.models import FactCandidate, FactRecord


def test_catalogue_completeness():
    assert len(FIELD_CATALOGUE) == len(FieldPath)
    for field_path in FieldPath:
        assert field_path in FIELD_CATALOGUE
        definition = FIELD_CATALOGUE[field_path]
        assert isinstance(definition, FieldDefinition)
        assert definition.value_type in FieldValueType
        assert definition.cardinality in FieldCardinality
        assert definition.merge_strategy is not None
        assert definition.freshness_policy_days > 0
        assert 0 <= definition.minimum_accepted_confidence <= 100
        assert definition.description


def test_unique_field_paths():
    field_paths = [definition.field_path for definition in FIELD_CATALOGUE.values()]
    assert len(field_paths) == len(set(field_paths))


def test_field_catalogue_version_is_set():
    assert FIELD_CATALOGUE_VERSION == "v1"


def test_expected_group_counts():
    counts: dict[str, int] = {}
    for field_path in FieldPath:
        prefix = field_path.value.split(".")[0]
        counts[prefix] = counts.get(prefix, 0) + 1
    assert counts == {
        "identity": 6,
        "business": 8,
        "catalogue": 7,
        "operations": 7,
        "technology": 12,
        "organisation": 5,
        "growth": 7,
    }


def test_field_path_is_typed_everywhere():
    assert FactCandidate.model_fields["field_path"].annotation is FieldPath
    assert FactRecord.model_fields["field_path"].annotation is FieldPath
