"""AC-15: every centralized pattern rule has both a positive-match test
and a false-positive-prevention test.

Cross-checks every `rule_id` defined in each extractor family's
`patterns.py` `PATTERN_RULES` registry against a maintained map of which
test function (in that family's own `extractors/test_*.py` module) proves
a positive match, and which proves a rejected false positive.
"""

import importlib

import pytest

from app.modules.extraction.domain.extractors.business.patterns import (
    PATTERN_RULES as BUSINESS_RULES,
)
from app.modules.extraction.domain.extractors.catalogue.patterns import (
    PATTERN_RULES as CATALOGUE_RULES,
)
from app.modules.extraction.domain.extractors.growth.patterns import PATTERN_RULES as GROWTH_RULES
from app.modules.extraction.domain.extractors.identity.patterns import (
    TITLE_SEPARATOR_PATTERN,
    TRADING_AS_PATTERN,
)
from app.modules.extraction.domain.extractors.operations.patterns import (
    PATTERN_RULES as OPERATIONS_RULES,
)
from app.modules.extraction.domain.extractors.organisation.patterns import (
    PATTERN_RULES as ORGANISATION_RULES,
)

IDENTITY_RULES = {
    TITLE_SEPARATOR_PATTERN.rule_id: TITLE_SEPARATOR_PATTERN,
    TRADING_AS_PATTERN.rule_id: TRADING_AS_PATTERN,
}

# rule_id -> (test_module, positive_test_name, false_positive_test_name)
# `false_positive_test_name` is `None` for rules that don't have a
# dedicated bare false-positive fixture (their "avoid" behavior is
# instead proven by a context-requirement/negative-pattern unit test
# elsewhere in the same module).
COVERAGE_MAP: dict[str, tuple[str, str, str | None]] = {
    # Identity
    TITLE_SEPARATOR_PATTERN.rule_id: (
        "test_identity_extractors",
        "test_company_name_priority_chain",
        None,
    ),
    TRADING_AS_PATTERN.rule_id: (
        "test_identity_extractors",
        "test_trading_name_from_about_page",
        None,
    ),
    # Business
    "business.wholesale.explicit_program": (
        "test_business_extractors",
        "test_wholesale_positive",
        "test_wholesale_false_positive_rejected",
    ),
    "business.trade_accounts.explicit_program": (
        "test_business_extractors",
        "test_trade_account_positive",
        "test_wholesale_false_positive_rejected",
    ),
    "business.click_and_collect.explicit_offer": (
        "test_business_extractors",
        "test_click_and_collect_positive",
        "test_no_online_only_inference_from_missing_stores",
    ),
    "business.subscription.explicit_offer": (
        "test_business_extractors",
        "test_subscription_positive",
        "test_no_online_only_inference_from_missing_stores",
    ),
    "business.booking.explicit_offer": (
        "test_business_extractors",
        "test_booking_positive",
        "test_no_online_only_inference_from_missing_stores",
    ),
    "business.online_only.explicit_statement": (
        "test_business_extractors",
        "test_explicit_online_only",
        "test_no_online_only_inference_from_missing_stores",
    ),
    "business.custom_products.explicit_offer": (
        "test_business_extractors",
        "test_custom_product_positive",
        "test_no_online_only_inference_from_missing_stores",
    ),
    "business.wholesale.explicit_negative": (
        "..test_reconciliation",
        "test_explicit_false_accepted_with_evidence",
        None,
    ),
    "business.click_and_collect.explicit_negative": (
        "..test_reconciliation",
        "test_explicit_false_accepted_with_evidence",
        None,
    ),
    # Catalogue
    "catalogue.bundle_evidence.explicit_wording": (
        "test_catalogue_extractors",
        "test_bundle_signal",
        "test_collection_urls_never_counted_as_products",
    ),
    "catalogue.customization_evidence.explicit_wording": (
        "test_catalogue_extractors",
        "test_customization_form",
        "test_collection_urls_never_counted_as_products",
    ),
    # Operations
    "operations.pickup_available.explicit_offer": (
        "test_operations_extractors",
        "test_pickup_location",
        "test_stockist_not_counted_as_owned",
    ),
    "operations.warehouse_count.explicit_wording": (
        "test_operations_extractors",
        "test_warehouse_wording_classification",
        "test_showroom_wording_classification",
    ),
    "operations.showroom_count.explicit_wording": (
        "test_operations_extractors",
        "test_showroom_wording_classification",
        "test_warehouse_wording_classification",
    ),
    "operations.locations.stockist_wording": (
        "test_operations_extractors",
        "test_stockist_not_counted_as_owned",
        "test_json_ld_store_location",
    ),
    # Organisation
    "organisation.internal_it_status.explicit_technical_staff": (
        "test_organisation_extractors",
        "test_internal_it_detected",
        "test_no_internal_it_inference_from_absence",
    ),
    "organisation.internal_it_status.agency_credit": (
        "test_organisation_extractors",
        "test_internal_it_detected",
        "test_no_internal_it_inference_from_absence",
    ),
    # Growth
    "growth.hiring.expansion_context": (
        "test_growth_extractors",
        "test_hiring_signal_with_growth_context",
        "test_routine_vacancy_not_treated_as_expansion",
    ),
    "growth.new_store.opening_announcement": (
        "test_growth_extractors",
        "test_new_store_signal",
        "test_routine_vacancy_not_treated_as_expansion",
    ),
    "growth.warehouse_change.move_announcement": (
        "test_growth_extractors",
        "test_warehouse_move_signal",
        "test_routine_vacancy_not_treated_as_expansion",
    ),
    "growth.expansion.distribution_or_acquisition": (
        "test_growth_extractors",
        "test_old_announcement_marked_stale_via_freshness_policy",
        "test_routine_vacancy_not_treated_as_expansion",
    ),
    "growth.platform_migration.explicit_statement": (
        "test_growth_extractors",
        "test_platform_migration_signal",
        "test_routine_vacancy_not_treated_as_expansion",
    ),
    "growth.new_category.explicit_launch": (
        "test_growth_extractors",
        "test_publication_vs_event_date",
        "test_routine_vacancy_not_treated_as_expansion",
    ),
    "growth.subscription_launch.explicit_launch": (
        "test_growth_extractors",
        "test_publication_vs_event_date",
        "test_routine_vacancy_not_treated_as_expansion",
    ),
}

ALL_RULE_IDS = set(
    {
        **BUSINESS_RULES,
        **CATALOGUE_RULES,
        **GROWTH_RULES,
        **OPERATIONS_RULES,
        **ORGANISATION_RULES,
        **IDENTITY_RULES,
    }
)


def test_every_rule_id_has_coverage_map_entry():
    missing = ALL_RULE_IDS - set(COVERAGE_MAP)
    assert not missing, f"rule_ids missing from COVERAGE_MAP: {missing}"


@pytest.mark.parametrize("rule_id", sorted(ALL_RULE_IDS))
def test_rule_has_positive_and_false_positive_tests(rule_id: str):
    module_name, positive_test, negative_test = COVERAGE_MAP[rule_id]
    if module_name.startswith(".."):
        full_module_name = f"tests.unit.extraction.{module_name[2:]}"
    else:
        full_module_name = f"tests.unit.extraction.extractors.{module_name}"
    module = importlib.import_module(full_module_name)
    assert hasattr(module, positive_test), f"{rule_id}: missing positive test {positive_test!r}"
    if negative_test is not None:
        assert hasattr(module, negative_test), (
            f"{rule_id}: missing false-positive test {negative_test!r}"
        )
