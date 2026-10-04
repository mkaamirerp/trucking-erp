"""Fuel provider catalog and tenant connection API schemas (Segment 0A)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class FuelConnectionFieldDef(BaseModel):
    key: str
    label: str
    type: str
    required: bool = False
    secret: bool = False


class FuelConnectionMethodDef(BaseModel):
    connection_method: str
    label: str
    evidence_status: str
    selectable: bool
    live_adapter_implemented: bool
    test_connection_capability: bool
    sync_capability: bool
    scheduling_capability: bool
    fields: list[FuelConnectionFieldDef]


class FuelProviderCatalogOut(BaseModel):
    provider_code: str
    display_name: str
    enabled: bool
    supported_connection_methods: list[str]
    unverified_connection_methods: list[str] = Field(default_factory=list)
    default_connection_method: str | None = None
    parser_profile_code: str | None = None
    expected_file_formats: list[str] = Field(default_factory=list)
    filename_pattern: str | None = None
    instructions: str
    live_adapter_implemented: bool
    connection_methods: list[FuelConnectionMethodDef]


class FuelSecretStateOut(BaseModel):
    configured: bool
    masked_display: str | None = None


class FuelProviderConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    provider_code: str
    connection_method: str
    display_name: str | None = None
    account_reference: str | None = None
    enabled: bool
    auto_sync_enabled: bool
    sync_frequency: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, FuelSecretStateOut] = Field(default_factory=dict)
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_result: str | None = None
    last_tested_at: datetime | None = None
    last_test_status: str | None = None
    last_test_result: str | None = None
    created_at: datetime
    updated_at: datetime


class FuelProviderConnectionWrite(BaseModel):
    provider_code: str = Field(min_length=1, max_length=40)
    connection_method: str = Field(min_length=1, max_length=40)
    enabled: bool = False
    auto_sync_enabled: bool = False
    sync_frequency: str | None = Field(default=None, max_length=40)
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider_code", "connection_method")
    @classmethod
    def _upper_codes(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("sync_frequency")
    @classmethod
    def _empty_freq_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class FuelProviderConnectionUpdate(BaseModel):
    connection_method: str | None = Field(default=None, max_length=40)
    enabled: bool | None = None
    auto_sync_enabled: bool | None = None
    sync_frequency: str | None = Field(default=None, max_length=40)
    fields: dict[str, Any] | None = None

    @field_validator("connection_method")
    @classmethod
    def _upper_method(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip().upper()

    @field_validator("sync_frequency")
    @classmethod
    def _empty_freq_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class FuelAdapterActionOut(BaseModel):
    success: bool
    attempted: bool
    result: str
    provider_code: str
    connection_method: str
    message: str


def _reject_float_decimal(value: Any) -> Any:
    if isinstance(value, float) and not isinstance(value, bool):
        raise ValueError("Fuel amounts must use Decimal or a decimal string, never float.")
    return value


class FuelSourceBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    provider_code: str
    provider_connection_id: int | None = None
    account_reference: str | None = None
    source_type: str
    invoice_number: str | None = None
    invoice_date: date | None = None
    statement_start: date | None = None
    statement_end: date | None = None
    due_date: date | None = None
    source_storage_ref: str | None = None
    source_hash: str | None = None
    remote_filename: str | None = None
    remote_timestamp: str | None = None
    imported_at: datetime
    parser_rule_version: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class FuelTransactionOut(BaseModel):
    """Canonical transaction. JSON money/quantity fields are decimal strings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    batch_id: int
    provider_transaction_identity: str | None = None
    source_row_order: int
    source_row_id: str | None = None
    source_vendor: str
    account_reference: str | None = None
    provider_event_type_raw: str | None = None
    provider_event_type: str
    transaction_datetime_source: str
    transaction_timezone_source: str
    transaction_timezone: str | None = None
    transaction_utc_offset: str | None = None
    transaction_date: date | None = None
    transaction_datetime: datetime | None = None
    unit_number_snapshot: str | None = None
    card_or_account_id: str | None = None
    driver_name_snapshot: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    provider_discount_rate: Decimal | None = None
    provider_discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    hst_amount: Decimal | None = None
    gst_amount: Decimal | None = None
    pst_amount: Decimal | None = None
    qst_amount: Decimal | None = None
    missed_discount_amount: Decimal | None = None
    out_of_network_fee: Decimal | None = None
    pre_tax_amount: Decimal | None = None
    billed_amount: Decimal | None = None
    retail_amount: Decimal | None = None
    total_amount: Decimal | None = None
    # Derived O/O pricing/settlement; not provider source. Parser must not hydrate it.
    owner_operator_charge_amount: Decimal | None = None
    oo_pricing_mode: str | None = None
    oo_pricing_rule_id: int | None = None
    oo_pricing_rule_version: str | None = None
    oo_charge_unit_price: Decimal | None = None
    oo_benefit_per_unit: Decimal | None = None
    oo_pricing_status: str | None = None
    oo_pricing_reason: str | None = None
    oo_pricing_inputs_json: dict[str, Any] | None = None
    quantity_unit: str | None = None
    unit_price_basis: str | None = None
    currency_raw: str | None = None
    currency: str | None = None
    processing_network: str | None = None
    merchant_network: str | None = None
    provider_raw: dict[str, Any] = Field(default_factory=dict)
    truck_id: int | None = None
    driver_id: int | None = None
    owner_operator_payee_id: int | None = None
    classification: str | None = None
    financial_responsibility: str | None = None
    settlement_deduction_candidate: bool | None = None
    settlement_deduction_basis_amount: Decimal | None = None
    pricing_agreement_ref: str | None = None
    settlement_ref: str | None = None
    downstream_module: str | None = None
    downstream_ack_status: str | None = None
    downstream_ack_ref: str | None = None
    gate_status: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "quantity",
        "unit_price",
        "provider_discount_rate",
        "provider_discount_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "missed_discount_amount",
        "out_of_network_fee",
        "pre_tax_amount",
        "billed_amount",
        "retail_amount",
        "total_amount",
        "owner_operator_charge_amount",
        "oo_charge_unit_price",
        "oo_benefit_per_unit",
        mode="before",
    )
    @classmethod
    def _no_float_money(cls, v: Any) -> Any:
        return _reject_float_decimal(v)

    @field_serializer(
        "quantity",
        "unit_price",
        "provider_discount_rate",
        "provider_discount_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "missed_discount_amount",
        "out_of_network_fee",
        "pre_tax_amount",
        "billed_amount",
        "retail_amount",
        "total_amount",
        "owner_operator_charge_amount",
        "oo_charge_unit_price",
        "oo_benefit_per_unit",
        when_used="json",
    )
    def _decimal_as_string(self, v: Decimal | None) -> str | None:
        return None if v is None else format(v, "f")


class FuelOwnerOperatorPricingRuleOut(BaseModel):
    """Effective-dated O/O fuel pricing agreement (Segment 4)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    owner_operator_payee_id: int
    pricing_mode: str
    fixed_discount_per_unit: Decimal | None = None
    percent_of_provider_discount: Decimal | None = None
    rule_version: str | None = None
    effective_from: datetime
    effective_to: datetime | None = None
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "fixed_discount_per_unit",
        "percent_of_provider_discount",
        mode="before",
    )
    @classmethod
    def _no_float_money(cls, v: Any) -> Any:
        return _reject_float_decimal(v)

    @field_serializer(
        "fixed_discount_per_unit",
        "percent_of_provider_discount",
        when_used="json",
    )
    def _decimal_as_string(self, v: Decimal | None) -> str | None:
        return None if v is None else format(v, "f")


class FuelTransactionSourceHydration(BaseModel):
    """Parser/source payload only. Derived pricing/resolution fields are forbidden."""

    model_config = ConfigDict(extra="forbid")

    provider_transaction_identity: str | None = None
    source_row_order: int
    source_row_id: str | None = None
    source_vendor: str
    account_reference: str | None = None
    provider_event_type_raw: str | None = None
    transaction_datetime_source: str
    transaction_timezone_source: str
    transaction_timezone: str | None = None
    transaction_utc_offset: str | None = None
    transaction_date: date | None = None
    unit_number_snapshot: str | None = None
    card_or_account_id: str | None = None
    driver_name_snapshot: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    provider_discount_rate: Decimal | None = None
    provider_discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    hst_amount: Decimal | None = None
    gst_amount: Decimal | None = None
    pst_amount: Decimal | None = None
    qst_amount: Decimal | None = None
    missed_discount_amount: Decimal | None = None
    out_of_network_fee: Decimal | None = None
    pre_tax_amount: Decimal | None = None
    billed_amount: Decimal | None = None
    retail_amount: Decimal | None = None
    total_amount: Decimal | None = None
    quantity_unit: str | None = None
    unit_price_basis: str | None = None
    currency_raw: str | None = None
    provider_raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "quantity",
        "unit_price",
        "provider_discount_rate",
        "provider_discount_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "missed_discount_amount",
        "out_of_network_fee",
        "pre_tax_amount",
        "billed_amount",
        "retail_amount",
        "total_amount",
        mode="before",
    )
    @classmethod
    def _no_float_money(cls, v: Any) -> Any:
        return _reject_float_decimal(v)


class FuelSourceControlOut(BaseModel):
    """Provider control total. JSON money/quantity fields are decimal strings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    batch_id: int
    source_vendor: str
    account_reference: str | None = None
    provider_control_identity: str | None = None
    control_label_raw: str | None = None
    control_type_raw: str | None = None
    control_type: str
    control_scope_raw: str | None = None
    control_scope: str
    scope_card_or_account_id: str | None = None
    scope_unit_number_snapshot: str | None = None
    scope_product_raw: str | None = None
    invoice_number: str | None = None
    source_row_order: int | None = None
    source_row_id: str | None = None
    currency_raw: str | None = None
    currency: str | None = None
    quantity: Decimal | None = None
    declared_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    hst_amount: Decimal | None = None
    gst_amount: Decimal | None = None
    pst_amount: Decimal | None = None
    qst_amount: Decimal | None = None
    discount_amount: Decimal | None = None
    pre_tax_amount: Decimal | None = None
    provider_raw: dict[str, Any] = Field(default_factory=dict)
    requires_review: bool = False
    review_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "quantity",
        "declared_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "discount_amount",
        "pre_tax_amount",
        mode="before",
    )
    @classmethod
    def _no_float_money(cls, v: Any) -> Any:
        return _reject_float_decimal(v)

    @field_serializer(
        "quantity",
        "declared_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "discount_amount",
        "pre_tax_amount",
        when_used="json",
    )
    def _decimal_as_string(self, v: Decimal | None) -> str | None:
        return None if v is None else format(v, "f")


class FuelSourceControlHydration(BaseModel):
    """Parser/source control payload only. Not a purchase transaction."""

    model_config = ConfigDict(extra="forbid")

    source_vendor: str
    account_reference: str | None = None
    provider_control_identity: str | None = None
    control_label_raw: str | None = None
    control_type_raw: str | None = None
    control_scope_raw: str | None = None
    scope_card_or_account_id: str | None = None
    scope_unit_number_snapshot: str | None = None
    scope_product_raw: str | None = None
    invoice_number: str | None = None
    source_row_order: int | None = None
    source_row_id: str | None = None
    currency_raw: str | None = None
    quantity: Decimal | None = None
    declared_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    hst_amount: Decimal | None = None
    gst_amount: Decimal | None = None
    pst_amount: Decimal | None = None
    qst_amount: Decimal | None = None
    discount_amount: Decimal | None = None
    pre_tax_amount: Decimal | None = None
    provider_raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "quantity",
        "declared_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "discount_amount",
        "pre_tax_amount",
        mode="before",
    )
    @classmethod
    def _no_float_money(cls, v: Any) -> Any:
        return _reject_float_decimal(v)


# --- Segment 8: source review queue ---


class FuelReviewQueueItemOut(BaseModel):
    batch_id: int
    tenant_id: int
    provider_code: str
    source_type: str
    invoice_number: str | None = None
    invoice_date: date | None = None
    statement_start: date | None = None
    statement_end: date | None = None
    account_reference: str | None = None
    remote_filename: str | None = None
    source_storage_ref: str | None = None
    parser_rule_version: str | None = None
    provider_profile_code: str | None = None
    layout_status: str | None = None
    status: str
    review_version: int
    currencies: list[str] = Field(default_factory=list)
    transaction_count: int = 0
    control_count: int = 0
    pending_review_count: int = 0
    problem_count: int = 0
    layout_problems: list[str] = Field(default_factory=list)
    problem_summary: dict[str, Any] = Field(default_factory=dict)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_started_by: str | None = None
    review_started_at: datetime | None = None
    imported_at: datetime


class FuelReviewCorrectionIn(BaseModel):
    field: str = Field(min_length=1, max_length=64)
    reviewed_value: Any = None
    reason: str = Field(min_length=1)

    @field_validator("field")
    @classmethod
    def _strip_field(cls, v: str) -> str:
        return v.strip()

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Correction reason is required")
        return s

    @field_validator("reviewed_value", mode="before")
    @classmethod
    def _no_float(cls, v: Any) -> Any:
        return _reject_float_decimal(v)


class FuelReviewConfirmIn(BaseModel):
    expected_version: int | None = None
    corrections: list[FuelReviewCorrectionIn] = Field(default_factory=list)


class FuelReviewStartIn(BaseModel):
    expected_version: int | None = None


class FuelReviewProcessIn(BaseModel):
    expected_version: int | None = None


class FuelReviewDocumentOut(BaseModel):
    source_storage_ref: str | None = None
    remote_filename: str | None = None
    source_type: str | None = None
    immutable: bool = True
    note: str | None = None


class FuelReviewWorkspaceOut(BaseModel):
    batch: FuelReviewQueueItemOut
    rows: list[dict[str, Any]]
    current_row: dict[str, Any] | None = None
    progress: dict[str, Any]
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    document: FuelReviewDocumentOut
    process_boundary: dict[str, Any]


class FuelReviewConfirmOut(BaseModel):
    batch_id: int
    review_version: int
    confirmed: dict[str, Any]
    next_row: dict[str, Any] | None = None
    progress: dict[str, Any]
    batch_status: str


class FuelReviewProcessOut(BaseModel):
    batch_id: int
    status: str
    review_version: int
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    reconciliation_implemented: bool = False
    finalization_implemented: bool = False
    message: str


# --- Segment 9: reconciliation ---


class FuelReconciliationRunIn(BaseModel):
    """Empty body reserved for future options; Segment 9 needs no input flags."""

    model_config = ConfigDict(extra="forbid")


class FuelReconciliationOut(BaseModel):
    outcome: str
    status: str
    batch_id: int
    tenant_id: int
    provider_code: str
    transaction_count: int
    control_count: int
    gates: list[dict[str, Any]] = Field(default_factory=list)
    unexplained_variances: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    currencies: list[str] = Field(default_factory=list)
    validated_totals_by_currency: dict[str, str] = Field(default_factory=dict)
    provider_totals_by_currency: dict[str, str] = Field(default_factory=dict)
    finalization_implemented: bool = False
    financial_responsibility_implemented: bool = False
    ai_authority: bool = False
    reconciled_at: str | None = None
    reconciled_by: str | None = None


# --- BVD Implementation 1 (source fidelity) ---


class FuelDashboardStatsOut(BaseModel):
    needs_review_count: int
    processed_last_7_days_count: int


class FuelProcessedCurrencyTotalOut(BaseModel):
    currency: str
    amount: str


class FuelProcessedCurrencyFinancialOut(BaseModel):
    """Per-currency statement money (no FX); canonical purchase rollups."""

    currency: str
    total_amount: str
    discount_amount: str | None = None


class FuelProcessedSummaryOut(BaseModel):
    """Provider-neutral post-wall processed Fuel summary (canonical authority)."""

    batch_id: int
    provider_code: str
    source_import_ref: str | None = None
    source_storage_ref: str | None = None
    account_reference: str | None = None
    invoice_number: str
    period_start: str | None = None
    period_end: str | None = None
    due_date: str | None = None
    finalized_at: str | None = None
    batch_status: str
    transaction_count: int
    control_count: int
    currency_totals: list[FuelProcessedCurrencyTotalOut] = Field(default_factory=list)
    currency_financial_summaries: list[FuelProcessedCurrencyFinancialOut] = Field(
        default_factory=list
    )
    provider_control_totals: list[FuelProcessedCurrencyTotalOut] = Field(default_factory=list)
    cad_transaction_total: str | None = None
    usd_transaction_total: str | None = None
    usd_provider_control: str | None = None
    purchase_card_count: int = 0
    purchase_card_numbers: list[str] = Field(default_factory=list)
    total_amount: str = ""
    currency: str | None = None
    read_only: bool = True
    review_status: str = "SOURCE_REVIEWED"


class FuelBvdImportOut(BaseModel):
    import_id: str
    row_count: int
    parse_status: str


class FuelBvdImportListItemOut(BaseModel):
    import_id: str
    invoice_number: str
    review_status: str
    uploaded_at: str | None = None
    source_file_name: str | None = None


class FuelBvdCompletedBasicLineOut(BaseModel):
    key: str
    label: str
    amount: str


class FuelBvdCompletedBasicOut(BaseModel):
    provider: str
    import_id: str
    invoice_number: str
    review_status: str
    read_only: bool
    processed_at: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    card_number: str | None = None
    purchase_card_count: int = 0
    purchase_card_numbers: list[str] = Field(default_factory=list)
    due_date: str | None = None
    invoice_disc_amt: str = ""
    unit_count: int
    unit_numbers: list[str] = Field(default_factory=list)
    total_amount: str
    currency: str | None = None
    categories: list[FuelBvdCompletedBasicLineOut] = Field(default_factory=list)
    taxes: list[FuelBvdCompletedBasicLineOut] = Field(default_factory=list)
    account_code: str | None = None
    usd_transaction_total: str | None = None
    cad_transaction_total: str | None = None
    usd_provider_control: str | None = None
    transaction_count: int | None = None
    control_count: int | None = None


class FuelBvdRowOut(BaseModel):
    id: int
    import_id: str
    row_type: str
    source_file_name: str | None = None
    source_file_sha256: str | None = None
    source_storage_ref: str | None = None
    source_page: int | None = None
    source_row_number: int | None = None
    parse_status: str | None = None
    parser_version: str | None = None
    extraction_warnings: dict[str, Any] | None = None

    invoice_number: str | None = None
    invoice_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    due_date: str | None = None
    client_name: str | None = None
    client_address: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    card_number: str | None = None
    hst_number: str | None = None
    qst_number: str | None = None
    auth_code: str | None = None
    driver_name: str | None = None
    unit_number: str | None = None
    transaction_date: str | None = None
    site_number: str | None = None
    site_name: str | None = None
    site_city: str | None = None
    prov_st: str | None = None
    prod: str | None = None
    qty: str | None = None
    retail: str | None = None
    billed: str | None = None
    pre_tax_amt: str | None = None
    hst: str | None = None
    gst: str | None = None
    pst: str | None = None
    qst: str | None = None
    disc_rate: str | None = None
    disc_amt: str | None = None
    final_amt: str | None = None
    cur: str | None = None
    row_label: str | None = None
    product: str | None = None
    final_amount: str | None = None
    legend_code: str | None = None
    legend_product_name: str | None = None
    express_code: str | None = None
    express_tractor: str | None = None
    express_trailer: str | None = None
    express_cdl: str | None = None
    express_trip_number: str | None = None
    amount_cashed: str | None = None
    express_fee: str | None = None
    payee_raw: str | None = None
    notes_raw: str | None = None

    review_status: str | None = None
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    field_corrections: dict[str, Any] | None = None


class FuelBvdCorrectionItemIn(BaseModel):
    fuel_bvd_id: int
    field_name: str
    reviewed_value: str
    correction_reason: str | None = None


class FuelBvdReviewSaveIn(BaseModel):
    corrections: list[FuelBvdCorrectionItemIn] = Field(default_factory=list)


class FuelBvdReviewSummaryOut(BaseModel):
    import_id: str
    invoice_number: str
    row_count: int
    transaction_count: int
    correction_count: int
    review_status: str
    final_amount: str | None = None
    currency: str | None = None


class FuelBvdSourceReconciliationOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    passed: bool
    transaction_total: str
    all_unit_total: str
    provider_grand_total: str | None = None
    difference: str
    checks: list[dict[str, Any]] = Field(default_factory=list)
    currencies_seen: list[str] = Field(default_factory=list)


class FuelNationwideImportOut(BaseModel):
    import_id: str
    row_count: int
    parse_status: str


class FuelNationwideRowOut(BaseModel):
    id: int
    import_id: str
    row_type: str
    source_page: int | None = None
    source_row_number: int | None = None
    parse_status: str | None = None
    parser_version: str | None = None
    review_status: str | None = None
    account_code: str | None = None
    invoice_number: str | None = None
    invoice_start_date: str | None = None
    invoice_end_date: str | None = None
    due_date: str | None = None
    customer_name: str | None = None
    card_number: str | None = None
    unit_number: str | None = None
    transaction_date: str | None = None
    city: str | None = None
    prov_st: str | None = None
    product: str | None = None
    volume: str | None = None
    ex_gst_per_unit: str | None = None
    total: str | None = None
    network: str | None = None
    currency: str | None = None
    usa_discount: str | None = None
    missed_disc: str | None = None
    oon_fees: str | None = None
    control_type: str | None = None
    row_label: str | None = None
    control_line_raw: str | None = None
    declared_amount: str | None = None
    gst: str | None = None
    pst: str | None = None
    qst: str | None = None
    control_volume: str | None = None
    field_corrections: dict[str, Any] | None = None


class FuelNationwideCorrectionItemIn(BaseModel):
    fuel_nationwide_id: int
    field_name: str
    reviewed_value: str
    correction_reason: str | None = None


class FuelNationwideReviewSaveIn(BaseModel):
    corrections: list[FuelNationwideCorrectionItemIn] = Field(default_factory=list)


class FuelNationwideReviewSummaryOut(BaseModel):
    import_id: str
    invoice_number: str | None = None
    row_count: int
    transaction_count: int
    correction_count: int
    review_status: str
    account_code: str | None = None


class FuelNationwideSourceReconciliationOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    usd_row_total_sum: str | None = None
    usd_precision_extension: str | None = None
    usd_provider_control: str | None = None
    usd_precision_difference: str | None = None
    cad_ex_tax_extension: str | None = None
    cad_ex_tax_control: str | None = None
    cad_gst: str | None = None
    cad_pst: str | None = None
    cad_subtotal: str | None = None


class FuelChargeCategoryOut(BaseModel):
    code: str
    display_name: str
    description: str | None = None
    active: bool = True


class FuelCanonicalTransactionOut(BaseModel):
    id: int
    batch_id: int
    source_row_id: str | None = None
    source_vendor: str | None = None
    provider_section_raw: str | None = None
    provider_transaction_identity: str | None = None
    provider_reason_raw: str | None = None
    product_code_raw: str | None = None
    principal_amount: Decimal | None = None
    provider_fee_amount: Decimal | None = None
    unit_price: Decimal | None = None
    billed_amount: Decimal | None = None
    retail_amount: Decimal | None = None
    provider_discount_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency_raw: str | None = None
    classification: str | None = None
    classification_status: str | None = None
    classification_source: str | None = None

    @field_serializer(
        "principal_amount",
        "provider_fee_amount",
        "unit_price",
        "billed_amount",
        "retail_amount",
        "provider_discount_amount",
        "total_amount",
        when_used="json",
    )
    def _serialize_money(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return format(value, "f")


class FuelProcessedOperationalTransactionOut(BaseModel):
    """Provider-neutral TruckERP processed-Fuel workspace row (Checkpoint 1).

    Sourced only from ``fuel_transactions``. No provider-native staging tables.
    """

    id: int
    batch_id: int
    source_row_order: int
    source_row_id: str | None = None
    source_vendor: str

    transaction_date: str | None = None
    transaction_datetime_source: str
    transaction_timezone_source: str | None = None

    unit_number_snapshot: str | None = None
    card_or_account_id: str | None = None
    driver_id: int | None = None
    truck_id: int | None = None
    owner_operator_payee_id: int | None = None

    city: str | None = None
    province_state: str | None = None
    country: str | None = None
    merchant_site: str | None = None

    product: str | None = None
    product_code_raw: str | None = None

    quantity: str | None = None
    quantity_unit: str | None = None
    unit_price: str | None = None

    total_amount: str | None = None
    currency: str | None = None
    principal_amount: str | None = None
    provider_fee_amount: str | None = None

    classification: str | None = None
    classification_status: str | None = None

    financial_responsibility: str | None = None
    owner_operator_charge_amount: str | None = None
    settlement_deduction_candidate: bool | None = None
    settlement_deduction_basis_amount: str | None = None

    @field_serializer(
        "quantity",
        "unit_price",
        "total_amount",
        "principal_amount",
        "provider_fee_amount",
        "owner_operator_charge_amount",
        "settlement_deduction_basis_amount",
        when_used="json",
    )
    def _serialize_operational_money(self, value: str | Decimal | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value, "f")
        return value


# JSON field contract for Checkpoint 1 tests (BVD / Nationwide / TEST_PROVIDER must match).
OPERATIONAL_TRANSACTION_FIELD_NAMES: frozenset[str] = frozenset(
    FuelProcessedOperationalTransactionOut.model_fields.keys()
)


class FuelProcessedDetailOut(FuelProcessedSummaryOut):
    canonical_transactions: list[FuelCanonicalTransactionOut] = Field(default_factory=list)
    operational_transactions: list[FuelProcessedOperationalTransactionOut] = Field(default_factory=list)


class FuelTransactionClassificationIn(BaseModel):
    canonical_category: str = Field(min_length=1, max_length=64)
    remember_mapping: bool = False
    apply_matching_in_import: bool = False


class FuelReasonGroupClassificationIn(BaseModel):
    provider_section_raw: str = Field(min_length=1, max_length=255)
    provider_reason_raw: str = Field(min_length=1, max_length=255)
    canonical_category: str = Field(min_length=1, max_length=64)
    remember_mapping: bool = False


class FuelClassificationSummaryOut(BaseModel):
    import_id: str
    confirmed: int
    needs_review: int
    total: int


class FuelUnresolvedReasonGroupOut(BaseModel):
    provider_code: str
    provider_section_raw: str
    provider_reason_raw: str
    normalized_reason_key: str
    transaction_count: int
    total_amount: str
    transaction_ids: list[int]
    classification: str | None = None


class FuelClassificationAuditEventOut(BaseModel):
    id: int
    fuel_transaction_id: int
    provider_reason_raw: str | None = None
    previous_category: str | None = None
    proposed_category: str
    source: str | None = None
    mapping_id: int | None = None
    actor_user_id: str | None = None
    created_at: str | None = None
    remember_mapping: bool | None = None
    apply_matching_in_import: bool | None = None


def _format_fuel_decimal(amount: Decimal | None) -> str | None:
    if amount is None:
        return None
    return format(amount, "f")


def _iso_fuel_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def fuel_transaction_to_canonical_out(txn: Any) -> FuelCanonicalTransactionOut:
    return FuelCanonicalTransactionOut(
        id=txn.id,
        batch_id=txn.batch_id,
        source_row_id=txn.source_row_id,
        source_vendor=getattr(txn, "source_vendor", None),
        provider_section_raw=txn.provider_section_raw,
        provider_transaction_identity=txn.provider_transaction_identity,
        provider_reason_raw=txn.provider_reason_raw,
        product_code_raw=txn.product_code_raw,
        principal_amount=txn.principal_amount,
        provider_fee_amount=txn.provider_fee_amount,
        unit_price=txn.unit_price,
        billed_amount=txn.billed_amount,
        retail_amount=txn.retail_amount,
        provider_discount_amount=txn.provider_discount_amount,
        total_amount=txn.total_amount,
        currency_raw=txn.currency_raw,
        classification=txn.classification,
        classification_status=txn.classification_status,
        classification_source=txn.classification_source,
    )


class FuelManualEntryStageOut(BaseModel):
    stage_id: str
    provider_code: str
    status: str
    entry_method: str
    draft: dict[str, Any] = Field(default_factory=dict)
    extraction_raw: dict[str, Any] | None = None
    validation_snapshot: dict[str, Any] | None = None
    requires_review: bool = False
    source_file_name: str | None = None
    has_receipt_attachment: bool = False
    processed_batch_id: int | None = None
    expires_at: str | None = None


class FuelManualEntryDraftPatchIn(BaseModel):
    draft: dict[str, Any] = Field(default_factory=dict)


class FuelManualEntryProcessOut(BaseModel):
    batch_id: int
    transaction_id: int
    provider_code: str
    status: str
    parser_version: str | None = None


class FuelManualEntryValidateOut(BaseModel):
    ok: bool = True
    requires_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    derived_fields: dict[str, str] = Field(default_factory=dict)


def fuel_transaction_to_operational_out(txn: Any) -> FuelProcessedOperationalTransactionOut:
    """Map one ``fuel_transactions`` row to the TruckERP operational workspace contract."""
    return FuelProcessedOperationalTransactionOut(
        id=txn.id,
        batch_id=txn.batch_id,
        source_row_order=txn.source_row_order,
        source_row_id=txn.source_row_id,
        source_vendor=txn.source_vendor,
        transaction_date=_iso_fuel_date(txn.transaction_date),
        transaction_datetime_source=txn.transaction_datetime_source,
        transaction_timezone_source=txn.transaction_timezone_source,
        unit_number_snapshot=txn.unit_number_snapshot,
        card_or_account_id=txn.card_or_account_id,
        driver_id=txn.driver_id,
        truck_id=txn.truck_id,
        owner_operator_payee_id=txn.owner_operator_payee_id,
        city=txn.city,
        province_state=txn.province_state,
        country=txn.country,
        merchant_site=txn.merchant_site,
        product=txn.product,
        product_code_raw=txn.product_code_raw,
        quantity=_format_fuel_decimal(txn.quantity),
        quantity_unit=txn.quantity_unit,
        unit_price=_format_fuel_decimal(txn.unit_price),
        total_amount=_format_fuel_decimal(txn.total_amount),
        currency=txn.currency,
        principal_amount=_format_fuel_decimal(txn.principal_amount),
        provider_fee_amount=_format_fuel_decimal(txn.provider_fee_amount),
        classification=txn.classification,
        classification_status=txn.classification_status,
        financial_responsibility=txn.financial_responsibility,
        owner_operator_charge_amount=_format_fuel_decimal(txn.owner_operator_charge_amount),
        settlement_deduction_candidate=txn.settlement_deduction_candidate,
        settlement_deduction_basis_amount=_format_fuel_decimal(txn.settlement_deduction_basis_amount),
    )
