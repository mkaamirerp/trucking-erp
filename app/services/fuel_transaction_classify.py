"""Provider-neutral fuel transaction classification (Segment B). No money mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.services.fuel_bvd_canonical_projection import BVD_VENDOR, SECTION_EXPRESS, SECTION_FUEL_CARD
from app.services.fuel_charge_categories import (
    CATEGORY_DEF,
    CATEGORY_FUEL,
    CATEGORY_SCALE,
    CATEGORY_UNMAPPED,
    CLASSIFICATION_SOURCE_PROVIDER_RULE,
    CLASSIFICATION_SOURCE_TENANT_MAPPING,
    CLASSIFICATION_STATUS_CONFIRMED,
    CLASSIFICATION_STATUS_UNMAPPED,
)
from app.services.fuel_reason_normalize import normalize_provider_reason_key

BVD_PURCHASE_PRODUCT_CATEGORY: dict[str, str] = {
    "TA": CATEGORY_FUEL,
    "TF": CATEGORY_FUEL,
    "DF": CATEGORY_DEF,
    "S": CATEGORY_SCALE,
}


@dataclass(frozen=True, slots=True)
class FuelTransactionClassificationResult:
    classification: str
    classification_status: str
    classification_source: str | None
    mapping_id: int | None = None


def _unmapped() -> FuelTransactionClassificationResult:
    return FuelTransactionClassificationResult(
        classification=CATEGORY_UNMAPPED,
        classification_status=CLASSIFICATION_STATUS_UNMAPPED,
        classification_source=None,
        mapping_id=None,
    )


def _confirmed(
    category: str,
    source: str,
    *,
    mapping_id: int | None = None,
) -> FuelTransactionClassificationResult:
    return FuelTransactionClassificationResult(
        classification=category,
        classification_status=CLASSIFICATION_STATUS_CONFIRMED,
        classification_source=source,
        mapping_id=mapping_id,
    )


def classify_bvd_purchase_product(product_code_raw: str | None) -> FuelTransactionClassificationResult:
    code = (product_code_raw or "").strip().upper()
    if not code:
        return _unmapped()
    category = BVD_PURCHASE_PRODUCT_CATEGORY.get(code)
    if category is None:
        return _unmapped()
    return _confirmed(category, CLASSIFICATION_SOURCE_PROVIDER_RULE)


def classify_fuel_transaction(
    *,
    tenant_id: int,
    provider_code: str,
    provider_section_raw: str | None,
    product_code_raw: str | None,
    provider_reason_raw: str | None,
    tenant_reason_mappings: Mapping[tuple[str, str, str], tuple[str, int]] | None = None,
) -> FuelTransactionClassificationResult:
    """Resolve category without modifying money or operational assignments.

    Resolution order: documented provider rule → tenant mapping → UNMAPPED.
    """
    _ = tenant_id  # reserved for future tenant-specific provider rules
    provider = (provider_code or "").strip().upper()
    section = (provider_section_raw or "").strip()

    if provider == BVD_VENDOR and section == SECTION_FUEL_CARD:
        return classify_bvd_purchase_product(product_code_raw)

    if provider == BVD_VENDOR and section == SECTION_EXPRESS:
        key = normalize_provider_reason_key(provider_reason_raw)
        if key and tenant_reason_mappings:
            hit = tenant_reason_mappings.get((provider, section, key))
            if hit is not None:
                category, mapping_id = hit
                return _confirmed(
                    category,
                    CLASSIFICATION_SOURCE_TENANT_MAPPING,
                    mapping_id=mapping_id,
                )
        return _unmapped()

    return _unmapped()
