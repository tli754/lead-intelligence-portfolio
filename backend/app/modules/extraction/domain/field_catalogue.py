"""The typed, versioned catalogue of every supported extraction field path.

`FieldPath` is the **only** vocabulary allowed for a "which fact are we
talking about" value anywhere in this module — `FactCandidate.field_path`/
`FactRecord.field_path` are typed as `FieldPath`, never a bare `str`
(brief section 3's explicit "do not use arbitrary string field paths").

Built first (T1), per the contract's suggested implementation order —
nothing else in this module can validate against the catalogue otherwise.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.modules.extraction.domain.enums import VerificationState
from app.modules.extraction.domain.reconciliation_rules import MergeStrategy

FIELD_CATALOGUE_VERSION = "v1"

# Suggested confidence-acceptance thresholds, brief section 15.
THRESHOLD_AUTHORITATIVE_EXACT = 70
THRESHOLD_CONTACT_INFO = 70
THRESHOLD_BOOLEAN_CAPABILITY = 65
THRESHOLD_TECHNOLOGY = 70
THRESHOLD_CATALOGUE_ESTIMATE = 55
THRESHOLD_GROWTH = 65
THRESHOLD_DETERMINISTIC_INFERENCE = 50

# Suggested freshness windows (days), brief section 18.
FRESHNESS_IDENTITY_DAYS = 365
FRESHNESS_PLATFORM_DAYS = 180
FRESHNESS_CONTACT_DAYS = 180
FRESHNESS_BUSINESS_CAPABILITIES_DAYS = 180
FRESHNESS_PHYSICAL_LOCATIONS_DAYS = 180
FRESHNESS_TECHNOLOGY_DAYS = 90
FRESHNESS_CATALOGUE_ESTIMATE_DAYS = 30
FRESHNESS_GROWTH_DAYS = 90
FRESHNESS_CAREERS_DAYS = 30

_ALL_VERIFICATION_STATES: list[VerificationState] = list(VerificationState)


class FieldPath(StrEnum):
    """Every supported dot-path field, exactly brief section 3's 52 entries."""

    # Identity (6)
    IDENTITY_COMPANY_NAME = "identity.company_name"
    IDENTITY_TRADING_NAME = "identity.trading_name"
    IDENTITY_PLATFORM = "identity.platform"
    IDENTITY_COUNTRY = "identity.country"
    IDENTITY_CITY = "identity.city"
    IDENTITY_LANGUAGE = "identity.language"

    # Business (8)
    BUSINESS_WHOLESALE = "business.wholesale"
    BUSINESS_TRADE_ACCOUNTS = "business.trade_accounts"
    BUSINESS_CLICK_AND_COLLECT = "business.click_and_collect"
    BUSINESS_SUBSCRIPTION = "business.subscription"
    BUSINESS_BOOKING = "business.booking"
    BUSINESS_ONLINE_ONLY = "business.online_only"
    BUSINESS_CUSTOM_PRODUCTS = "business.custom_products"
    BUSINESS_BRANDS = "business.brands"

    # Catalogue (7)
    CATALOGUE_PRODUCT_COUNT = "catalogue.product_count"
    CATALOGUE_PRODUCT_COUNT_ESTIMATE = "catalogue.product_count_estimate"
    CATALOGUE_SKU_COUNT_ESTIMATE = "catalogue.sku_count_estimate"
    CATALOGUE_VARIANT_EVIDENCE = "catalogue.variant_evidence"
    CATALOGUE_COLLECTION_COUNT = "catalogue.collection_count"
    CATALOGUE_BUNDLE_EVIDENCE = "catalogue.bundle_evidence"
    CATALOGUE_CUSTOMIZATION_EVIDENCE = "catalogue.customization_evidence"

    # Physical operations (7)
    OPERATIONS_RETAIL_STORE_COUNT = "operations.retail_store_count"
    OPERATIONS_SHOWROOM_COUNT = "operations.showroom_count"
    OPERATIONS_WAREHOUSE_COUNT = "operations.warehouse_count"
    OPERATIONS_OFFICE_COUNT = "operations.office_count"
    OPERATIONS_PICKUP_AVAILABLE = "operations.pickup_available"
    OPERATIONS_RETURNS_LOCATION_COUNT = "operations.returns_location_count"
    OPERATIONS_LOCATIONS = "operations.locations"

    # Technology (12)
    TECHNOLOGY_COMMERCE_PLATFORM = "technology.commerce_platform"
    TECHNOLOGY_PAYMENT_PROVIDERS = "technology.payment_providers"
    TECHNOLOGY_CRM = "technology.crm"
    TECHNOLOGY_ERP = "technology.erp"
    TECHNOLOGY_ACCOUNTING = "technology.accounting"
    TECHNOLOGY_REVIEW_PLATFORMS = "technology.review_platforms"
    TECHNOLOGY_SUPPORT_TOOLS = "technology.support_tools"
    TECHNOLOGY_ANALYTICS = "technology.analytics"
    TECHNOLOGY_LOYALTY = "technology.loyalty"
    TECHNOLOGY_EMAIL_MARKETING = "technology.email_marketing"
    TECHNOLOGY_AI_SIGNALS = "technology.ai_signals"
    TECHNOLOGY_FRAMEWORKS = "technology.frameworks"

    # Organisation (5)
    ORGANISATION_EMAILS = "organisation.emails"
    ORGANISATION_PHONE_NUMBERS = "organisation.phone_numbers"
    ORGANISATION_PEOPLE = "organisation.people"
    ORGANISATION_INTERNAL_IT_STATUS = "organisation.internal_it_status"
    ORGANISATION_RECOMMENDED_CONTACT_CANDIDATES = "organisation.recommended_contact_candidates"

    # Growth (7)
    GROWTH_HIRING = "growth.hiring"
    GROWTH_EXPANSION = "growth.expansion"
    GROWTH_NEW_STORE = "growth.new_store"
    GROWTH_WAREHOUSE_CHANGE = "growth.warehouse_change"
    GROWTH_PLATFORM_MIGRATION = "growth.platform_migration"
    GROWTH_NEW_CATEGORY = "growth.new_category"
    GROWTH_SUBSCRIPTION_LAUNCH = "growth.subscription_launch"


class FieldValueType(StrEnum):
    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    ENUM = "enum"
    STRING_LIST = "string_list"
    STRUCTURED_ENTITY = "structured_entity"
    STRUCTURED_ENTITY_LIST = "structured_entity_list"


class FieldCardinality(StrEnum):
    SCALAR = "scalar"
    ARRAY = "array"


class FieldDefinition(BaseModel):
    field_path: FieldPath
    value_type: FieldValueType
    cardinality: FieldCardinality
    allowed_verification_states: list[VerificationState] = Field(
        default_factory=lambda: list(_ALL_VERIFICATION_STATES)
    )
    merge_strategy: MergeStrategy
    freshness_policy_days: int
    minimum_accepted_confidence: int = Field(ge=0, le=100)
    sensitive: bool = False
    description: str


def _definition(
    field_path: FieldPath,
    *,
    value_type: FieldValueType,
    cardinality: FieldCardinality,
    merge_strategy: MergeStrategy,
    freshness_policy_days: int,
    minimum_accepted_confidence: int,
    description: str,
    sensitive: bool = False,
) -> FieldDefinition:
    return FieldDefinition(
        field_path=field_path,
        value_type=value_type,
        cardinality=cardinality,
        merge_strategy=merge_strategy,
        freshness_policy_days=freshness_policy_days,
        minimum_accepted_confidence=minimum_accepted_confidence,
        description=description,
        sensitive=sensitive,
    )


_SCALAR = FieldCardinality.SCALAR
_ARRAY = FieldCardinality.ARRAY

FIELD_CATALOGUE: dict[FieldPath, FieldDefinition] = {
    # --- Identity -----------------------------------------------------
    FieldPath.IDENTITY_COMPANY_NAME: _definition(
        FieldPath.IDENTITY_COMPANY_NAME,
        value_type=FieldValueType.STRING,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.SCALAR_CONFLICT_PRESERVING,
        freshness_policy_days=FRESHNESS_IDENTITY_DAYS,
        minimum_accepted_confidence=THRESHOLD_AUTHORITATIVE_EXACT,
        description="The company's registered/legal or primary trading display name.",
    ),
    FieldPath.IDENTITY_TRADING_NAME: _definition(
        FieldPath.IDENTITY_TRADING_NAME,
        value_type=FieldValueType.STRING,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.SCALAR_CONFLICT_PRESERVING,
        freshness_policy_days=FRESHNESS_IDENTITY_DAYS,
        minimum_accepted_confidence=THRESHOLD_AUTHORITATIVE_EXACT,
        description="A distinct 'trading as' name, kept separate from the legal company name.",
    ),
    FieldPath.IDENTITY_PLATFORM: _definition(
        FieldPath.IDENTITY_PLATFORM,
        value_type=FieldValueType.STRING,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.SCALAR_CONFLICT_PRESERVING,
        freshness_policy_days=FRESHNESS_PLATFORM_DAYS,
        minimum_accepted_confidence=THRESHOLD_AUTHORITATIVE_EXACT,
        description="The company's self-described primary commerce platform, if stated.",
    ),
    FieldPath.IDENTITY_COUNTRY: _definition(
        FieldPath.IDENTITY_COUNTRY,
        value_type=FieldValueType.STRING,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.SCALAR_CONFLICT_PRESERVING,
        freshness_policy_days=FRESHNESS_IDENTITY_DAYS,
        minimum_accepted_confidence=THRESHOLD_AUTHORITATIVE_EXACT,
        description="Company's primary operating country. TLD alone never reaches 'verified'.",
    ),
    FieldPath.IDENTITY_CITY: _definition(
        FieldPath.IDENTITY_CITY,
        value_type=FieldValueType.STRING,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.SCALAR_CONFLICT_PRESERVING,
        freshness_policy_days=FRESHNESS_IDENTITY_DAYS,
        minimum_accepted_confidence=THRESHOLD_AUTHORITATIVE_EXACT,
        description="Company's primary operating city. Never inferred from a phone area code.",
    ),
    FieldPath.IDENTITY_LANGUAGE: _definition(
        FieldPath.IDENTITY_LANGUAGE,
        value_type=FieldValueType.STRING,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.SCALAR_PREFERRED,
        freshness_policy_days=FRESHNESS_IDENTITY_DAYS,
        minimum_accepted_confidence=THRESHOLD_DETERMINISTIC_INFERENCE,
        description="Primary page language, from html[lang]/content-language only.",
    ),
    # --- Business -------------------------------------------------------
    FieldPath.BUSINESS_WHOLESALE: _definition(
        FieldPath.BUSINESS_WHOLESALE,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_EXPLICIT,
        freshness_policy_days=FRESHNESS_BUSINESS_CAPABILITIES_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Whether the company offers a wholesale program.",
    ),
    FieldPath.BUSINESS_TRADE_ACCOUNTS: _definition(
        FieldPath.BUSINESS_TRADE_ACCOUNTS,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_EXPLICIT,
        freshness_policy_days=FRESHNESS_BUSINESS_CAPABILITIES_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Whether the company offers trade/professional accounts.",
    ),
    FieldPath.BUSINESS_CLICK_AND_COLLECT: _definition(
        FieldPath.BUSINESS_CLICK_AND_COLLECT,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_EXPLICIT,
        freshness_policy_days=FRESHNESS_BUSINESS_CAPABILITIES_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Whether click-and-collect / in-store pickup is offered.",
    ),
    FieldPath.BUSINESS_SUBSCRIPTION: _definition(
        FieldPath.BUSINESS_SUBSCRIPTION,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_EXPLICIT,
        freshness_policy_days=FRESHNESS_BUSINESS_CAPABILITIES_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Whether a recurring/subscription purchase option is offered.",
    ),
    FieldPath.BUSINESS_BOOKING: _definition(
        FieldPath.BUSINESS_BOOKING,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_EXPLICIT,
        freshness_policy_days=FRESHNESS_BUSINESS_CAPABILITIES_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Whether appointment/consultation booking is offered.",
    ),
    FieldPath.BUSINESS_ONLINE_ONLY: _definition(
        FieldPath.BUSINESS_ONLINE_ONLY,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_EXPLICIT,
        freshness_policy_days=FRESHNESS_BUSINESS_CAPABILITIES_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description=(
            "Whether the company explicitly states it has no physical retail presence. "
            "Never inferred merely from an absent store-locator page."
        ),
    ),
    FieldPath.BUSINESS_CUSTOM_PRODUCTS: _definition(
        FieldPath.BUSINESS_CUSTOM_PRODUCTS,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_EXPLICIT,
        freshness_policy_days=FRESHNESS_BUSINESS_CAPABILITIES_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Whether personalization/custom-made products are offered.",
    ),
    FieldPath.BUSINESS_BRANDS: _definition(
        FieldPath.BUSINESS_BRANDS,
        value_type=FieldValueType.STRING_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.SET_UNION,
        freshness_policy_days=FRESHNESS_BUSINESS_CAPABILITIES_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Explicit list of brands the company stocks/carries.",
    ),
    # --- Catalogue --------------------------------------------------------
    FieldPath.CATALOGUE_PRODUCT_COUNT: _definition(
        FieldPath.CATALOGUE_PRODUCT_COUNT,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_CATALOGUE_ESTIMATE_DAYS,
        minimum_accepted_confidence=THRESHOLD_CATALOGUE_ESTIMATE,
        description="Exact or estimated total product count.",
    ),
    FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE: _definition(
        FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_CATALOGUE_ESTIMATE_DAYS,
        minimum_accepted_confidence=THRESHOLD_CATALOGUE_ESTIMATE,
        description="A lower-confidence, explicitly-estimated product count.",
    ),
    FieldPath.CATALOGUE_SKU_COUNT_ESTIMATE: _definition(
        FieldPath.CATALOGUE_SKU_COUNT_ESTIMATE,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_CATALOGUE_ESTIMATE_DAYS,
        minimum_accepted_confidence=THRESHOLD_CATALOGUE_ESTIMATE,
        description="Estimated SKU count (product count x observed median variants).",
    ),
    FieldPath.CATALOGUE_VARIANT_EVIDENCE: _definition(
        FieldPath.CATALOGUE_VARIANT_EVIDENCE,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_POSITIVE_ONLY,
        freshness_policy_days=FRESHNESS_CATALOGUE_ESTIMATE_DAYS,
        minimum_accepted_confidence=THRESHOLD_CATALOGUE_ESTIMATE,
        description="Whether product variant selectors/offers were observed.",
    ),
    FieldPath.CATALOGUE_COLLECTION_COUNT: _definition(
        FieldPath.CATALOGUE_COLLECTION_COUNT,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_CATALOGUE_ESTIMATE_DAYS,
        minimum_accepted_confidence=THRESHOLD_CATALOGUE_ESTIMATE,
        description="Count of product collections/categories.",
    ),
    FieldPath.CATALOGUE_BUNDLE_EVIDENCE: _definition(
        FieldPath.CATALOGUE_BUNDLE_EVIDENCE,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_POSITIVE_ONLY,
        freshness_policy_days=FRESHNESS_CATALOGUE_ESTIMATE_DAYS,
        minimum_accepted_confidence=THRESHOLD_CATALOGUE_ESTIMATE,
        description="Whether bundle/kit/multipack product wording was observed.",
    ),
    FieldPath.CATALOGUE_CUSTOMIZATION_EVIDENCE: _definition(
        FieldPath.CATALOGUE_CUSTOMIZATION_EVIDENCE,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_POSITIVE_ONLY,
        freshness_policy_days=FRESHNESS_CATALOGUE_ESTIMATE_DAYS,
        minimum_accepted_confidence=THRESHOLD_CATALOGUE_ESTIMATE,
        description="Whether product-customization form controls were observed.",
    ),
    # --- Physical operations ------------------------------------------------
    FieldPath.OPERATIONS_RETAIL_STORE_COUNT: _definition(
        FieldPath.OPERATIONS_RETAIL_STORE_COUNT,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_PHYSICAL_LOCATIONS_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Count of company-owned retail stores (stockists excluded).",
    ),
    FieldPath.OPERATIONS_SHOWROOM_COUNT: _definition(
        FieldPath.OPERATIONS_SHOWROOM_COUNT,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_PHYSICAL_LOCATIONS_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Count of showrooms.",
    ),
    FieldPath.OPERATIONS_WAREHOUSE_COUNT: _definition(
        FieldPath.OPERATIONS_WAREHOUSE_COUNT,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_PHYSICAL_LOCATIONS_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Count of warehouses (distinct from retail stores).",
    ),
    FieldPath.OPERATIONS_OFFICE_COUNT: _definition(
        FieldPath.OPERATIONS_OFFICE_COUNT,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_PHYSICAL_LOCATIONS_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Count of corporate/administrative offices.",
    ),
    FieldPath.OPERATIONS_PICKUP_AVAILABLE: _definition(
        FieldPath.OPERATIONS_PICKUP_AVAILABLE,
        value_type=FieldValueType.BOOLEAN,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.BOOLEAN_EXPLICIT,
        freshness_policy_days=FRESHNESS_PHYSICAL_LOCATIONS_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Whether at least one pickup location is available.",
    ),
    FieldPath.OPERATIONS_RETURNS_LOCATION_COUNT: _definition(
        FieldPath.OPERATIONS_RETURNS_LOCATION_COUNT,
        value_type=FieldValueType.INTEGER,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.NUMERIC_EXACT_OR_ESTIMATE,
        freshness_policy_days=FRESHNESS_PHYSICAL_LOCATIONS_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Count of distinct returns-acceptance locations.",
    ),
    FieldPath.OPERATIONS_LOCATIONS: _definition(
        FieldPath.OPERATIONS_LOCATIONS,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.STRUCTURED_ENTITY_MERGE,
        freshness_policy_days=FRESHNESS_PHYSICAL_LOCATIONS_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="Structured physical-location records (stores/showrooms/warehouses/offices).",
    ),
    # --- Technology ---------------------------------------------------------
    **{
        field_path: _definition(
            field_path,
            value_type=FieldValueType.STRING_LIST,
            cardinality=_ARRAY,
            merge_strategy=MergeStrategy.SET_UNION,
            freshness_policy_days=FRESHNESS_TECHNOLOGY_DAYS,
            minimum_accepted_confidence=THRESHOLD_TECHNOLOGY,
            description=f"Detected {label} products/technologies, set-union merged across pages.",
        )
        for field_path, label in {
            FieldPath.TECHNOLOGY_COMMERCE_PLATFORM: "commerce-platform",
            FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS: "payment-provider",
            FieldPath.TECHNOLOGY_CRM: "CRM/marketing",
            FieldPath.TECHNOLOGY_ERP: "ERP",
            FieldPath.TECHNOLOGY_ACCOUNTING: "accounting",
            FieldPath.TECHNOLOGY_REVIEW_PLATFORMS: "review-platform",
            FieldPath.TECHNOLOGY_SUPPORT_TOOLS: "support-tool",
            FieldPath.TECHNOLOGY_ANALYTICS: "analytics",
            FieldPath.TECHNOLOGY_LOYALTY: "loyalty",
            FieldPath.TECHNOLOGY_EMAIL_MARKETING: "email-marketing",
            FieldPath.TECHNOLOGY_AI_SIGNALS: "AI-signal",
            FieldPath.TECHNOLOGY_FRAMEWORKS: "frontend-framework",
        }.items()
    },
    # --- Organisation ---------------------------------------------------------
    FieldPath.ORGANISATION_EMAILS: _definition(
        FieldPath.ORGANISATION_EMAILS,
        value_type=FieldValueType.STRING_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.SET_UNION,
        freshness_policy_days=FRESHNESS_CONTACT_DAYS,
        minimum_accepted_confidence=THRESHOLD_CONTACT_INFO,
        description="Deduplicated business email addresses.",
        sensitive=True,
    ),
    FieldPath.ORGANISATION_PHONE_NUMBERS: _definition(
        FieldPath.ORGANISATION_PHONE_NUMBERS,
        value_type=FieldValueType.STRING_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.SET_UNION,
        freshness_policy_days=FRESHNESS_CONTACT_DAYS,
        minimum_accepted_confidence=THRESHOLD_CONTACT_INFO,
        description="Deduplicated business phone numbers.",
        sensitive=True,
    ),
    FieldPath.ORGANISATION_PEOPLE: _definition(
        FieldPath.ORGANISATION_PEOPLE,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.STRUCTURED_ENTITY_MERGE,
        freshness_policy_days=FRESHNESS_CONTACT_DAYS,
        minimum_accepted_confidence=THRESHOLD_CONTACT_INFO,
        description="Explicitly named people with role context.",
        sensitive=True,
    ),
    FieldPath.ORGANISATION_INTERNAL_IT_STATUS: _definition(
        FieldPath.ORGANISATION_INTERNAL_IT_STATUS,
        value_type=FieldValueType.ENUM,
        cardinality=_SCALAR,
        merge_strategy=MergeStrategy.SCALAR_CONFLICT_PRESERVING,
        freshness_policy_days=FRESHNESS_CONTACT_DAYS,
        minimum_accepted_confidence=THRESHOLD_BOOLEAN_CAPABILITY,
        description="detected/not_detected/unknown. Never inferred from absence alone.",
    ),
    FieldPath.ORGANISATION_RECOMMENDED_CONTACT_CANDIDATES: _definition(
        FieldPath.ORGANISATION_RECOMMENDED_CONTACT_CANDIDATES,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.STRUCTURED_ENTITY_MERGE,
        freshness_policy_days=FRESHNESS_CONTACT_DAYS,
        minimum_accepted_confidence=THRESHOLD_DETERMINISTIC_INFERENCE,
        description="Priority-ordered contact candidates. Never a single final recommendation.",
        sensitive=True,
    ),
    # --- Growth --------------------------------------------------------------
    FieldPath.GROWTH_HIRING: _definition(
        FieldPath.GROWTH_HIRING,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.TIME_SERIES,
        freshness_policy_days=FRESHNESS_CAREERS_DAYS,
        minimum_accepted_confidence=THRESHOLD_GROWTH,
        description="Hiring signals. Routine single vacancies are not treated as expansion.",
    ),
    FieldPath.GROWTH_EXPANSION: _definition(
        FieldPath.GROWTH_EXPANSION,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.TIME_SERIES,
        freshness_policy_days=FRESHNESS_GROWTH_DAYS,
        minimum_accepted_confidence=THRESHOLD_GROWTH,
        description="Distribution-expansion signals.",
    ),
    FieldPath.GROWTH_NEW_STORE: _definition(
        FieldPath.GROWTH_NEW_STORE,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.TIME_SERIES,
        freshness_policy_days=FRESHNESS_GROWTH_DAYS,
        minimum_accepted_confidence=THRESHOLD_GROWTH,
        description="New-store-opening signals.",
    ),
    FieldPath.GROWTH_WAREHOUSE_CHANGE: _definition(
        FieldPath.GROWTH_WAREHOUSE_CHANGE,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.TIME_SERIES,
        freshness_policy_days=FRESHNESS_GROWTH_DAYS,
        minimum_accepted_confidence=THRESHOLD_GROWTH,
        description="Warehouse move/expansion signals.",
    ),
    FieldPath.GROWTH_PLATFORM_MIGRATION: _definition(
        FieldPath.GROWTH_PLATFORM_MIGRATION,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.TIME_SERIES,
        freshness_policy_days=FRESHNESS_GROWTH_DAYS,
        minimum_accepted_confidence=THRESHOLD_GROWTH,
        description="Commerce-platform migration signals.",
    ),
    FieldPath.GROWTH_NEW_CATEGORY: _definition(
        FieldPath.GROWTH_NEW_CATEGORY,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.TIME_SERIES,
        freshness_policy_days=FRESHNESS_GROWTH_DAYS,
        minimum_accepted_confidence=THRESHOLD_GROWTH,
        description="New product-category entry signals.",
    ),
    FieldPath.GROWTH_SUBSCRIPTION_LAUNCH: _definition(
        FieldPath.GROWTH_SUBSCRIPTION_LAUNCH,
        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
        cardinality=_ARRAY,
        merge_strategy=MergeStrategy.TIME_SERIES,
        freshness_policy_days=FRESHNESS_GROWTH_DAYS,
        minimum_accepted_confidence=THRESHOLD_GROWTH,
        description="Subscription-program launch signals.",
    ),
}


def _validate_catalogue_completeness() -> None:
    missing = [field_path for field_path in FieldPath if field_path not in FIELD_CATALOGUE]
    if missing:
        raise RuntimeError(f"FIELD_CATALOGUE is missing definitions for: {missing}")
    orphaned = [key for key in FIELD_CATALOGUE if not isinstance(key, FieldPath)]
    if orphaned:
        raise RuntimeError(f"FIELD_CATALOGUE has non-FieldPath keys: {orphaned}")
    if len(FIELD_CATALOGUE) != len(FieldPath):
        raise RuntimeError("FIELD_CATALOGUE has duplicate or extra field-path entries")


_validate_catalogue_completeness()
