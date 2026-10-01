"""Nationwide source reconciliation — provider precision math (Decimal only)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.services.fuel_controls import CONTROL_TYPE_CARD_TOTAL, CONTROL_TYPE_UNKNOWN
from app.services.fuel_nationwide_import import ROW_CONTROL, ROW_HEADER, ROW_TRANSACTION
from app.services.fuel_money import quantize_money

_MONEY_RE = re.compile(r"\$([\d,]+\.\d{2})")


@dataclass
class NationwideReconciliationCheck:
    code: str
    status: str
    message: str
    expected: str | None = None
    actual: str | None = None


@dataclass
class NationwideSourceReconciliationResult:
    passed: bool
    checks: list[NationwideReconciliationCheck] = field(default_factory=list)
    usd_row_total_sum: str | None = None
    usd_precision_extension: str | None = None
    usd_provider_control: str | None = None
    usd_precision_difference: str | None = None
    cad_ex_tax_extension: str | None = None
    cad_ex_tax_control: str | None = None
    cad_gst: str | None = None
    cad_pst: str | None = None
    cad_subtotal: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "code": c.code,
                    "status": c.status,
                    "message": c.message,
                    "expected": c.expected,
                    "actual": c.actual,
                }
                for c in self.checks
            ],
            "usd_row_total_sum": self.usd_row_total_sum,
            "usd_precision_extension": self.usd_precision_extension,
            "usd_provider_control": self.usd_provider_control,
            "usd_precision_difference": self.usd_precision_difference,
            "cad_ex_tax_extension": self.cad_ex_tax_extension,
            "cad_ex_tax_control": self.cad_ex_tax_control,
            "cad_gst": self.cad_gst,
            "cad_pst": self.cad_pst,
            "cad_subtotal": self.cad_subtotal,
        }


def parse_nationwide_decimal(raw: Any) -> tuple[Decimal | None, str | None]:
    if raw is None:
        return None, None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None, None
    try:
        return Decimal(text), None
    except (InvalidOperation, ValueError):
        return None, "UNPARSEABLE"


def _round_money(value: Decimal) -> Decimal:
    return quantize_money(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _extension_sum(transactions: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for row in transactions:
        vol, _ = parse_nationwide_decimal(row.get("volume"))
        unit, _ = parse_nationwide_decimal(row.get("ex_gst_per_unit"))
        if vol is None or unit is None:
            continue
        total += vol * unit
    return total


def _card_total_declared(line: str | None) -> Decimal | None:
    if not line:
        return None
    amounts = [_money for _money in (_parse_money(m) for m in _MONEY_RE.findall(line)) if _money is not None]
    if not amounts:
        return None
    return amounts[0]


def _parse_money(text: str) -> Decimal | None:
    dec, err = parse_nationwide_decimal(text)
    return dec if not err else None


def _control_by_type(rows: list[dict[str, Any]], control_type: str) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("row_type") == ROW_CONTROL and r.get("control_type") == control_type]


def _control_line_prefix(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any] | None:
    p = prefix.casefold()
    for r in rows:
        if r.get("row_type") != ROW_CONTROL:
            continue
        line = (r.get("control_line_raw") or "").casefold()
        if line.startswith(p):
            return r
    return None


def _money_from_control_line(line: str | None) -> Decimal | None:
    if not line:
        return None
    m = re.search(r"\$([\d,]+\.\d{2})\s*$", line.strip()) or re.search(
        r"\$([\d,]+\.\d{2})", line.strip()
    )
    if not m:
        parts = line.split("$")
        if len(parts) > 1:
            return _parse_money(parts[-1])
        return None
    return _parse_money(m.group(1))


def reconcile_nationwide_source_rows(rows: list[dict[str, Any]]) -> NationwideSourceReconciliationResult:
    result = NationwideSourceReconciliationResult(passed=True)
    header = next((r for r in rows if r.get("row_type") == ROW_HEADER), None)
    if header is None:
        result.passed = False
        result.checks.append(
            NationwideReconciliationCheck("HEADER_MISSING", "FAIL", "HEADER row required")
        )
        return result

    transactions = [r for r in rows if r.get("row_type") == ROW_TRANSACTION]
    controls = [r for r in rows if r.get("row_type") == ROW_CONTROL]

    for ctl in controls:
        if ctl.get("control_type") in (None, "", CONTROL_TYPE_UNKNOWN):
            result.passed = False
            result.checks.append(
                NationwideReconciliationCheck(
                    "UNKNOWN_CONTROL",
                    "FAIL",
                    f"unclassified control: {ctl.get('control_line_raw')}",
                )
            )

    usd_txns = [t for t in transactions if (t.get("currency") or "").upper() == "USD"]
    cad_txns = [t for t in transactions if (t.get("currency") or "").upper() == "CAD"]

    usd_row_sum = sum((parse_nationwide_decimal(t.get("total"))[0] or Decimal("0") for t in usd_txns), Decimal("0"))
    result.usd_row_total_sum = format(usd_row_sum, "f")

    usd_ext = _extension_sum(usd_txns)
    usd_ext_rounded = _round_money(usd_ext)
    result.usd_precision_extension = format(usd_ext, "f")

    usd_billing = next(
        (c for c in controls if (c.get("row_label") or "") == "USD_BILLING_TOTAL"),
        None,
    )
    usd_control_amt: Decimal | None = None
    if usd_billing:
        usd_control_amt, _ = parse_nationwide_decimal(usd_billing.get("declared_amount"))
    if usd_control_amt is None:
        result.passed = False
        result.checks.append(
            NationwideReconciliationCheck("USD_BILLING_CONTROL_MISSING", "FAIL", "USD billing control required")
        )
    else:
        result.usd_provider_control = format(usd_control_amt, "f")
        diff = usd_ext_rounded - usd_control_amt
        result.usd_precision_difference = f"{_round_money(diff):.2f}"
        if usd_ext_rounded != usd_control_amt:
            result.passed = False
            result.checks.append(
                NationwideReconciliationCheck(
                    "USD_PRECISION_CONTROL",
                    "FAIL",
                    "ROUND(SUM(volume×unit),2) must equal USD billing control",
                    expected=format(usd_control_amt, "f"),
                    actual=format(usd_ext_rounded, "f"),
                )
            )
        else:
            result.checks.append(
                NationwideReconciliationCheck(
                    "USD_PRECISION_CONTROL",
                    "PASS",
                    "USD precision extension matches provider billing control",
                    expected=format(usd_control_amt, "f"),
                    actual=format(usd_ext_rounded, "f"),
                )
            )

    cad_ext = _extension_sum(cad_txns)
    cad_ext_rounded = _round_money(cad_ext)
    result.cad_ex_tax_extension = format(cad_ext, "f")

    ex_tax_ctl = _control_line_prefix(rows, "total ex-gst")
    ex_tax_amt = _money_from_control_line(ex_tax_ctl.get("control_line_raw") if ex_tax_ctl else None)
    if ex_tax_amt is None:
        result.passed = False
        result.checks.append(
            NationwideReconciliationCheck("CAD_EX_TAX_CONTROL_MISSING", "FAIL", "Total Ex-GST & PST control missing")
        )
    else:
        result.cad_ex_tax_control = format(ex_tax_amt, "f")
        if cad_ext_rounded != ex_tax_amt:
            result.passed = False
            result.checks.append(
                NationwideReconciliationCheck(
                    "CAD_EX_TAX",
                    "FAIL",
                    "CAD volume×unit rounded must match ex-tax control",
                    expected=format(ex_tax_amt, "f"),
                    actual=format(cad_ext_rounded, "f"),
                )
            )
        else:
            result.checks.append(NationwideReconciliationCheck("CAD_EX_TAX", "PASS", "CAD ex-tax control OK"))

    gst_ctl = _control_line_prefix(rows, "gst $")
    gst_amt = _money_from_control_line(gst_ctl.get("control_line_raw") if gst_ctl else None)
    pst_ctl = _control_line_prefix(rows, "pst $")
    pst_amt = _money_from_control_line(pst_ctl.get("control_line_raw") if pst_ctl else None) or Decimal("0")
    sub_ctl = _control_line_prefix(rows, "subtotal")
    sub_amt = _money_from_control_line(sub_ctl.get("control_line_raw") if sub_ctl else None)

    if gst_amt is not None:
        result.cad_gst = f"{_round_money(gst_amt):.2f}"
    if pst_amt is not None:
        result.cad_pst = f"{_round_money(pst_amt):.2f}"
    if sub_amt is not None:
        result.cad_subtotal = f"{_round_money(sub_amt):.2f}"

    if ex_tax_amt is not None and gst_amt is not None and sub_amt is not None:
        expected_sub = _round_money(ex_tax_amt + gst_amt + pst_amt)
        if expected_sub != sub_amt:
            result.passed = False
            result.checks.append(
                NationwideReconciliationCheck(
                    "CAD_TAX_SUBTOTAL",
                    "FAIL",
                    "ex-tax + GST + PST must equal subtotal",
                    expected=format(sub_amt, "f"),
                    actual=format(expected_sub, "f"),
                )
            )
        else:
            result.checks.append(NationwideReconciliationCheck("CAD_TAX_SUBTOTAL", "PASS", "CAD tax/subtotal OK"))

    card_controls = [c for c in controls if c.get("control_type") == CONTROL_TYPE_CARD_TOTAL]
    for ctl in card_controls:
        line = ctl.get("control_line_raw") or ""
        card = ctl.get("card_number")
        if not card and line:
            card = line.split()[0]
        if not card:
            continue
        if " GST " in line.upper():
            continue
        card_txns = [t for t in usd_txns if (t.get("card_number") or "").upper() == card.upper()]
        if not card_txns:
            continue
        ext = _round_money(_extension_sum(card_txns))
        declared = _card_total_declared(line)
        if declared is None:
            result.passed = False
            result.checks.append(
                NationwideReconciliationCheck(
                    "CARD_TOTAL_PARSE",
                    "FAIL",
                    f"cannot parse CARD_TOTAL for {card}",
                )
            )
            continue
        if ext != declared:
            result.passed = False
            result.checks.append(
                NationwideReconciliationCheck(
                    "CARD_TOTAL",
                    "FAIL",
                    f"card {card} extension mismatch",
                    expected=format(declared, "f"),
                    actual=format(ext, "f"),
                )
            )
        else:
            result.checks.append(
                NationwideReconciliationCheck(
                    "CARD_TOTAL",
                    "PASS",
                    f"card {card} OK",
                    expected=format(declared, "f"),
                    actual=format(ext, "f"),
                )
            )

    if len(transactions) != 12:
        result.passed = False
        result.checks.append(
            NationwideReconciliationCheck(
                "TRANSACTION_COUNT",
                "FAIL",
                "expected 12 purchase rows",
                expected="12",
                actual=str(len(transactions)),
            )
        )

    return result
