"""BVD source validation — parsed money must reconcile to provider totals (Decimal only).

Does not post, categorize, or map to TruckERP fuel canonical rows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Literal

from app.services.fuel_bvd_extraction import (
    ROW_EXPRESS_SUBTOTAL,
    ROW_EXPRESS_TRANSACTION,
    ROW_GRAND_TOTAL,
    ROW_PAGE1_SUMMARY,
    ROW_TRANSACTION,
    ROW_TRANSACTION_SUBTOTAL,
)

LINE_ARITHMETIC_TOLERANCE: Final[Decimal] = Decimal("0.05")

CheckStatus = Literal["PASS", "FAIL", "NA", "INFO"]

UNASSIGNED_UNIT_KEY: Final[str] = "__UNASSIGNED__"
MANUAL_EXPRESS_LABELS: Final[frozenset[str]] = frozenset({"Manual", "Express"})

ADDITIVE_MONEY_FIELDS: Final[tuple[str, ...]] = (
    "qty",
    "pre_tax_amt",
    "hst",
    "gst",
    "pst",
    "qst",
    "disc_amt",
    "final_amt",
)

# Provider Grand Total row uses final_amount; transactions use final_amt.
PROVIDER_GRAND_FIELD_MAP: Final[tuple[tuple[str, str], ...]] = (
    ("qty", "qty"),
    ("pre_tax_amt", "pre_tax_amt"),
    ("hst", "hst"),
    ("gst", "gst"),
    ("pst", "pst"),
    ("qst", "qst"),
    ("disc_amt", "disc_amt"),
    ("final_amount", "final_amt"),
)


@dataclass
class ReconciliationCheck:
    code: str
    status: CheckStatus
    expected: str | None = None
    actual: str | None = None
    difference: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "status": self.status,
            "expected": self.expected,
            "actual": self.actual,
            "difference": self.difference,
            "detail": self.detail,
        }


@dataclass
class MoneyBucket:
    qty: Decimal = field(default_factory=lambda: Decimal("0"))
    pre_tax_amt: Decimal = field(default_factory=lambda: Decimal("0"))
    hst: Decimal = field(default_factory=lambda: Decimal("0"))
    gst: Decimal = field(default_factory=lambda: Decimal("0"))
    pst: Decimal = field(default_factory=lambda: Decimal("0"))
    qst: Decimal = field(default_factory=lambda: Decimal("0"))
    disc_amt: Decimal = field(default_factory=lambda: Decimal("0"))
    final_amt: Decimal = field(default_factory=lambda: Decimal("0"))

    def add_row(self, row: dict[str, Any], *, final_field: str = "final_amt") -> list[str]:
        """Add parsed additive columns; return parse error codes (empty if ok)."""
        errors: list[str] = []
        for col in ADDITIVE_MONEY_FIELDS:
            if col == "final_amt":
                raw = row.get(final_field)
                if raw is None or str(raw).strip() == "":
                    raw = row.get("final_amt")
            else:
                raw = row.get(col)
            dec, err = parse_bvd_decimal(raw)
            if err:
                errors.append(f"{col}:{err}")
                continue
            if dec is None:
                continue
            setattr(self, col, getattr(self, col) + dec)
        return errors

    def to_dict(self) -> dict[str, str]:
        return {k: decimal_to_display(getattr(self, k)) for k in ADDITIVE_MONEY_FIELDS}


def parse_bvd_decimal(raw: Any) -> tuple[Decimal | None, str | None]:
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    normalized = text.replace(",", "")
    try:
        return Decimal(normalized), None
    except (InvalidOperation, ValueError):
        return None, "UNPARSEABLE"


def decimal_to_display(value: Decimal) -> str:
    return format(value, "f")


def _row_get(row: dict[str, Any], key: str) -> str | None:
    val = row.get(key)
    if val is None or val == "":
        return None
    return str(val)


def _is_nonzero_money(raw: Any) -> bool:
    dec, err = parse_bvd_decimal(raw)
    if err or dec is None:
        return False
    return dec != Decimal("0")


def _compare_decimal(expected: Decimal, actual: Decimal) -> tuple[bool, Decimal]:
    diff = actual - expected
    return diff == Decimal("0"), diff


def _add_check(
    checks: list[ReconciliationCheck],
    *,
    code: str,
    expected: Decimal,
    actual: Decimal,
    required: bool = True,
    tolerance: Decimal | None = None,
) -> None:
    ok, diff = _compare_decimal(expected, actual)
    if tolerance is not None and not ok and abs(diff) <= tolerance:
        ok = True
        diff = Decimal("0")
    status: CheckStatus = "PASS" if ok else ("FAIL" if required else "INFO")
    checks.append(
        ReconciliationCheck(
            code=code,
            status=status,
            expected=decimal_to_display(expected),
            actual=decimal_to_display(actual),
            difference=decimal_to_display(abs(diff)),
        )
    )


def _provider_product_grand_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("row_type") != ROW_GRAND_TOTAL:
            continue
        label = (_row_get(row, "row_label") or "").strip()
        if label in ("Grand Total", "Grand Totals") or label in MANUAL_EXPRESS_LABELS:
            continue
        key = label or (_row_get(row, "product") or "").strip()
        if key:
            out[key] = row
    return out


def _provider_grand_total_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if row.get("row_type") != ROW_GRAND_TOTAL:
            continue
        if (_row_get(row, "row_label") or "").strip() == "Grand Total":
            return row
    return None


def _page1_control_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels_of_interest = {"Fuel Total", "Sub Total"}
    out: list[dict[str, Any]] = []
    for row in rows:
        rt = row.get("row_type")
        if rt == ROW_PAGE1_SUMMARY and (_row_get(row, "row_label") or "") in labels_of_interest:
            out.append(row)
        elif rt == ROW_TRANSACTION_SUBTOTAL and (_row_get(row, "row_label") or "") == "SUBTOTAL":
            # Only product-level SUBTOTAL TA style — skip per-auth SUBTOTAL lines for control compare
            if _row_get(row, "product"):
                out.append(row)
    return out


@dataclass
class BvdSourceReconciliationResult:
    passed: bool
    transaction_total: str
    all_unit_total: str
    provider_grand_total: str | None
    difference: str
    units: dict[str, dict[str, str]]
    unit_products: dict[str, dict[str, dict[str, str]]]
    products: dict[str, dict[str, str]]
    checks: list[ReconciliationCheck]
    currencies_seen: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "transaction_total": self.transaction_total,
            "all_unit_total": self.all_unit_total,
            "provider_grand_total": self.provider_grand_total,
            "difference": self.difference,
            "units": self.units,
            "unit_products": self.unit_products,
            "products": self.products,
            "checks": [c.to_dict() for c in self.checks],
            "currencies_seen": self.currencies_seen,
        }


def reconcile_bvd_source_rows(rows: list[dict[str, Any]]) -> BvdSourceReconciliationResult:
    checks: list[ReconciliationCheck] = []
    transactions = [r for r in rows if r.get("row_type") == ROW_TRANSACTION]

    txn_total_bucket = MoneyBucket()
    product_buckets: dict[str, MoneyBucket] = defaultdict(MoneyBucket)
    unit_buckets: dict[str, MoneyBucket] = defaultdict(MoneyBucket)
    unit_product_buckets: dict[str, dict[str, MoneyBucket]] = defaultdict(lambda: defaultdict(MoneyBucket))
    currencies: set[str] = set()

    parse_errors: list[str] = []
    missing_unit_nonzero = False

    for row in transactions:
        cur = _row_get(row, "cur")
        if cur:
            currencies.add(cur)

        final_raw = row.get("final_amt")
        final_dec, final_err = parse_bvd_decimal(final_raw)
        if final_err:
            parse_errors.append(f"txn:{row.get('id')}:final_amt:{final_err}")
        elif final_dec is None and _is_nonzero_money(final_raw):
            parse_errors.append(f"txn:{row.get('id')}:final_amt:MISSING")

        unit = (_row_get(row, "unit_number") or "").strip()
        prod = (_row_get(row, "prod") or "").strip() or "__BLANK_PROD__"

        if not unit and final_dec is not None and final_dec != Decimal("0"):
            missing_unit_nonzero = True
            unit = UNASSIGNED_UNIT_KEY

        if not unit:
            unit = UNASSIGNED_UNIT_KEY

        row_errors = txn_total_bucket.add_row(row)
        parse_errors.extend([f"txn:{row.get('id')}:{e}" for e in row_errors])

        product_buckets[prod].add_row(row)
        unit_buckets[unit].add_row(row)
        unit_product_buckets[unit][prod].add_row(row)

        # Per-transaction line arithmetic (informational when discount unverified).
        pre, _ = parse_bvd_decimal(row.get("pre_tax_amt"))
        hst, _ = parse_bvd_decimal(row.get("hst"))
        gst, _ = parse_bvd_decimal(row.get("gst"))
        pst, _ = parse_bvd_decimal(row.get("pst"))
        qst, _ = parse_bvd_decimal(row.get("qst"))
        disc, _ = parse_bvd_decimal(row.get("disc_amt"))
        if final_dec is not None and pre is not None:
            pre = pre or Decimal("0")
            hst = hst or Decimal("0")
            gst = gst or Decimal("0")
            pst = pst or Decimal("0")
            qst = qst or Decimal("0")
            disc = disc or Decimal("0")
            if disc != Decimal("0"):
                checks.append(
                    ReconciliationCheck(
                        code="TXN_LINE_ARITHMETIC",
                        status="INFO",
                        detail="Non-zero disc_amt; line arithmetic not enforced until verified on real BVD",
                        expected=None,
                        actual=decimal_to_display(final_dec),
                    )
                )
            else:
                expected_final = pre + hst + gst + pst + qst - disc
                txn_code = _row_get(row, "auth_code") or str(row.get("id") or "")
                _add_check(
                    checks,
                    code=f"TXN_LINE_ARITHMETIC_{txn_code}",
                    expected=expected_final,
                    actual=final_dec,
                    required=False,
                    tolerance=LINE_ARITHMETIC_TOLERANCE,
                )

    express_rows = [r for r in rows if r.get("row_type") == ROW_EXPRESS_TRANSACTION]
    express_subtotal_row = next(
        (r for r in rows if r.get("row_type") == ROW_EXPRESS_SUBTOTAL),
        None,
    )
    express_cashed_total = Decimal("0")
    express_fee_total = Decimal("0")
    express_final_total = Decimal("0")
    for row in express_rows:
        cashed, _ = parse_bvd_decimal(row.get("amount_cashed"))
        fee, _ = parse_bvd_decimal(row.get("express_fee"))
        final, _ = parse_bvd_decimal(row.get("final_amt"))
        express_cashed_total += cashed or Decimal("0")
        express_fee_total += fee or Decimal("0")
        express_final_total += final or Decimal("0")

    if express_rows:
        _add_check(
            checks,
            code="EXPRESS_ROW_COUNT",
            expected=Decimal(len(express_rows)),
            actual=Decimal(len(express_rows)),
        )
        if express_subtotal_row:
            sub_cashed, _ = parse_bvd_decimal(express_subtotal_row.get("amount_cashed"))
            sub_fee, _ = parse_bvd_decimal(express_subtotal_row.get("express_fee"))
            sub_final, _ = parse_bvd_decimal(express_subtotal_row.get("final_amt"))
            if sub_cashed is not None:
                _add_check(checks, code="EXPRESS_SUBTOTAL_CASHED", expected=sub_cashed, actual=express_cashed_total)
            if sub_fee is not None:
                _add_check(checks, code="EXPRESS_SUBTOTAL_FEE", expected=sub_fee, actual=express_fee_total)
            if sub_final is not None:
                _add_check(checks, code="EXPRESS_SUBTOTAL_TOTAL", expected=sub_final, actual=express_final_total)

    if parse_errors:
        checks.append(
            ReconciliationCheck(
                code="UNPARSEABLE_MONEY",
                status="FAIL",
                detail="; ".join(parse_errors[:20]),
            )
        )

    if missing_unit_nonzero:
        checks.append(
            ReconciliationCheck(
                code="MISSING_UNIT_NONZERO_FINAL",
                status="FAIL",
                detail="Transaction with non-zero final_amt has no unit_number",
            )
        )

    if len(currencies) > 1:
        checks.append(
            ReconciliationCheck(
                code="CURRENCY_MULTIPLE_WITHOUT_SPLIT",
                status="FAIL",
                detail=f"Multiple transaction currencies: {sorted(currencies)}",
            )
        )

    transaction_total = txn_total_bucket.final_amt
    all_unit_total = sum((b.final_amt for b in unit_buckets.values()), Decimal("0"))

    _add_check(
        checks,
        code="CORE_TXN_TOTAL_VS_UNIT_TOTAL",
        expected=transaction_total,
        actual=all_unit_total,
    )

    # Unit path: sum(unit_product) == unit total per unit.
    for unit, unit_bucket in unit_buckets.items():
        unit_prod_sum = sum((b.final_amt for b in unit_product_buckets[unit].values()), Decimal("0"))
        _add_check(
            checks,
            code=f"UNIT_PRODUCT_SUM_{unit}",
            expected=unit_bucket.final_amt,
            actual=unit_prod_sum,
        )

    product_txn_total = sum((b.final_amt for b in product_buckets.values()), Decimal("0"))
    _add_check(
        checks,
        code="CORE_TXN_TOTAL_VS_PRODUCT_TOTAL",
        expected=transaction_total,
        actual=product_txn_total,
    )

    provider_grand = _provider_grand_total_row(rows)
    provider_grand_final: Decimal | None = None
    if provider_grand:
        provider_grand_final, err = parse_bvd_decimal(
            provider_grand.get("final_amount") or provider_grand.get("final_amt")
        )
        if err:
            checks.append(
                ReconciliationCheck(
                    code="PROVIDER_GRAND_TOTAL_PARSE",
                    status="FAIL",
                    detail="Grand Total final_amount unparseable",
                )
            )
        else:
            invoice_final = transaction_total + express_final_total
            for provider_field, txn_field in PROVIDER_GRAND_FIELD_MAP:
                prov_dec, perr = parse_bvd_decimal(provider_grand.get(provider_field))
                if perr:
                    checks.append(
                        ReconciliationCheck(
                            code=f"PROVIDER_GRAND_{provider_field}_PARSE",
                            status="FAIL",
                            detail=perr,
                        )
                    )
                    continue
                if prov_dec is None:
                    continue
                if provider_field == "final_amount":
                    actual = invoice_final
                    required = True
                elif provider_field == "pre_tax_amt" and express_rows:
                    actual = txn_total_bucket.pre_tax_amt
                    required = False
                else:
                    actual = getattr(txn_total_bucket, txn_field if txn_field != "final_amt" else "final_amt")
                    if txn_field == "final_amt":
                        actual = txn_total_bucket.final_amt
                    required = provider_field != "pre_tax_amt"
                _add_check(
                    checks,
                    code=f"GRAND_TOTAL_{provider_field.upper()}",
                    expected=prov_dec,
                    actual=actual,
                    required=required,
                )
    else:
        checks.append(
            ReconciliationCheck(
                code="PROVIDER_GRAND_TOTAL_ROW",
                status="FAIL",
                detail="Missing row_label Grand Total",
            )
        )

    invoice_final_total = transaction_total + express_final_total
    if provider_grand_final is not None:
        _add_check(
            checks,
            code="CORE_PURCHASE_TOTAL",
            expected=transaction_total,
            actual=transaction_total,
        )
        _add_check(
            checks,
            code="CORE_INVOICE_FINAL_VS_PROVIDER_GRAND",
            expected=provider_grand_final,
            actual=invoice_final_total,
        )

    # Product breakdown vs provider GRAND_TOTAL rows.
    provider_products = _provider_product_grand_rows(rows)
    for prod_key, prov_row in provider_products.items():
        txn_bucket = product_buckets.get(prod_key)
        if txn_bucket is None:
            txn_bucket = MoneyBucket()
        for provider_field, txn_field in PROVIDER_GRAND_FIELD_MAP:
            prov_dec, perr = parse_bvd_decimal(prov_row.get(provider_field))
            if perr:
                checks.append(
                    ReconciliationCheck(
                        code=f"PRODUCT_{prod_key}_{provider_field}_PARSE",
                        status="FAIL",
                        detail=perr,
                    )
                )
                continue
            if prov_dec is None:
                continue
            actual = getattr(txn_bucket, txn_field if txn_field != "final_amt" else "final_amt")
            if txn_field == "final_amt":
                actual = txn_bucket.final_amt
            _add_check(
                checks,
                code=f"PRODUCT_{prod_key}_{provider_field.upper()}",
                expected=prov_dec,
                actual=actual,
            )

    # Manual / Express provider controls.
    for row in rows:
        if row.get("row_type") != ROW_GRAND_TOTAL:
            continue
        label = (_row_get(row, "row_label") or "").strip()
        if label not in MANUAL_EXPRESS_LABELS:
            continue
        amt, err = parse_bvd_decimal(row.get("final_amount") or row.get("final_amt"))
        if err:
            checks.append(
                ReconciliationCheck(
                    code=f"PROVIDER_{label.upper()}_PARSE",
                    status="FAIL",
                    detail=err,
                )
            )
        elif label == "Express" and amt is not None and express_rows:
            _add_check(
                checks,
                code="PROVIDER_EXPRESS_GRAND_VS_ROWS",
                expected=amt,
                actual=express_final_total,
            )
        elif label == "Manual" and amt is not None and amt != Decimal("0"):
            checks.append(
                ReconciliationCheck(
                    code="PROVIDER_MANUAL_UNRESOLVED",
                    status="FAIL",
                    detail="Non-zero Manual without verified allocation rule",
                    actual=decimal_to_display(amt),
                )
            )
        elif amt is not None and amt != Decimal("0"):
            checks.append(
                ReconciliationCheck(
                    code=f"PROVIDER_{label.upper()}_UNRESOLVED",
                    status="FAIL",
                    detail="Non-zero Manual/Express without verified allocation rule",
                    actual=decimal_to_display(amt),
                )
            )
        else:
            checks.append(
                ReconciliationCheck(
                    code=f"PROVIDER_{label.upper()}_ZERO",
                    status="PASS",
                    actual="0.00",
                )
            )

    card_txn_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in transactions:
        card = (_row_get(row, "card_number") or "").strip()
        if not card:
            continue
        final, _ = parse_bvd_decimal(row.get("final_amt"))
        if final is not None:
            card_txn_totals[card] += final

    for ctrl in _page1_control_rows(rows):
        label = _row_get(ctrl, "row_label") or "control"
        ctrl_final, err = parse_bvd_decimal(ctrl.get("final_amt"))
        if err:
            checks.append(
                ReconciliationCheck(
                    code=f"CONTROL_{label}_PARSE",
                    status="FAIL",
                    detail=err,
                )
            )
            continue
        if ctrl_final is None:
            continue
        card = (_row_get(ctrl, "card_number") or "").strip()
        if label == "Sub Total" and card:
            card_sum = card_txn_totals.get(card, Decimal("0"))
            _add_check(
                checks,
                code=f"CARD_{card}_SUB_TOTAL",
                expected=ctrl_final,
                actual=card_sum,
            )
        elif label == "Fuel Total" and card:
            checks.append(
                ReconciliationCheck(
                    code=f"CARD_{card}_FUEL_TOTAL_INFO",
                    status="INFO",
                    detail="Fuel Total is TA/fuel component only; card Sub Total is authoritative",
                    expected=decimal_to_display(ctrl_final),
                    actual=decimal_to_display(card_txn_totals.get(card, Decimal("0"))),
                )
            )

    diff = invoice_final_total - (provider_grand_final or Decimal("0"))
    diff_display = abs(diff)

    passed = not any(c.status == "FAIL" for c in checks)

    units_out = {u: b.to_dict() for u, b in unit_buckets.items() if u != UNASSIGNED_UNIT_KEY or b.final_amt != 0}
    if UNASSIGNED_UNIT_KEY in unit_buckets and unit_buckets[UNASSIGNED_UNIT_KEY].final_amt != 0:
        units_out[UNASSIGNED_UNIT_KEY] = unit_buckets[UNASSIGNED_UNIT_KEY].to_dict()

    unit_products_out: dict[str, dict[str, dict[str, str]]] = {}
    for unit, prod_map in unit_product_buckets.items():
        if unit == UNASSIGNED_UNIT_KEY and not missing_unit_nonzero:
            continue
        unit_products_out[unit] = {p: b.to_dict() for p, b in prod_map.items()}

    products_out = {p: b.to_dict() for p, b in product_buckets.items() if p != "__BLANK_PROD__"}
    if "__BLANK_PROD__" in product_buckets:
        products_out["__BLANK_PROD__"] = product_buckets["__BLANK_PROD__"].to_dict()

    return BvdSourceReconciliationResult(
        passed=passed,
        transaction_total=decimal_to_display(transaction_total),
        all_unit_total=decimal_to_display(all_unit_total),
        provider_grand_total=decimal_to_display(provider_grand_final) if provider_grand_final is not None else None,
        difference=decimal_to_display(diff_display),
        units=units_out,
        unit_products=unit_products_out,
        products=products_out,
        checks=checks,
        currencies_seen=sorted(currencies),
    )


def process_allowed(reconciliation: BvdSourceReconciliationResult) -> bool:
    """Process gate: required source validations must pass."""
    return reconciliation.passed
