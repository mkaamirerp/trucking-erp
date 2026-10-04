import type { FuelBvdRow } from "../../api";
import { displayCell, sortBvdRows } from "./bvdParsedDisplay";

export type BvdValidationStatus = "pass" | "fail" | "na";

export type BvdValidationMetric = {
  id: "invoice_amount" | "units_processed" | "cash_advance";
  label: string;
  value: string;
  /** Secondary line on dashboard cards (e.g. unit numbers). */
  subvalue?: string;
  status: BvdValidationStatus;
  detail?: string;
};

export type BvdParsedValidation = {
  metrics: BvdValidationMetric[];
  allPass: boolean;
};

const MONEY_EPS = 0.005;

export function parseBvdMoneyString(raw: string): number | null {
  const t = raw.replace(/,/g, "").replace(/\$/g, "").trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function rowMoney(row: FuelBvdRow | undefined, ...fields: string[]): number | null {
  if (!row) return null;
  for (const field of fields) {
    const parsed = parseBvdMoneyString(displayCell(row, field));
    if (parsed !== null) return parsed;
  }
  return null;
}

function nearlyEqual(a: number, b: number): boolean {
  return Math.abs(a - b) <= MONEY_EPS;
}

function formatMoney(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function sumTransactionFinalAmount(transactions: FuelBvdRow[]): number {
  let total = 0;
  for (const row of transactions) {
    total += parseBvdMoneyString(displayCell(row, "final_amt")) ?? 0;
  }
  return total;
}

function findPage1Summary(rows: FuelBvdRow[], rowLabel: string): FuelBvdRow | undefined {
  return rows.find((r) => r.row_type === "PAGE1_SUMMARY" && displayCell(r, "row_label") === rowLabel);
}

function findGrandTotalLabel(rows: FuelBvdRow[], rowLabel: string): FuelBvdRow | undefined {
  return rows.find((r) => r.row_type === "GRAND_TOTAL" && displayCell(r, "row_label") === rowLabel);
}

/** Deterministic checks from fuel_bvd rows only (Implementation 1 — no posting). */
export function computeBvdParsedValidation(rows: FuelBvdRow[]): BvdParsedValidation {
  const sorted = sortBvdRows(rows);
  const transactions = sorted.filter((r) => r.row_type === "TRANSACTION");

  const calculatedInvoice = sumTransactionFinalAmount(transactions);
  const fuelTotal = findPage1Summary(sorted, "Fuel Total");
  const subTotal = findPage1Summary(sorted, "Sub Total");
  const grandTotal = findGrandTotalLabel(sorted, "Grand Total");

  const declaredParts: { label: string; amount: number | null }[] = [
    { label: "transactions", amount: transactions.length ? calculatedInvoice : null },
    { label: "Fuel Total", amount: rowMoney(fuelTotal, "final_amt") },
    { label: "Sub Total", amount: rowMoney(subTotal, "final_amt") },
    { label: "Grand Total", amount: rowMoney(grandTotal, "final_amount", "final_amt") },
  ];

  const amounts = declaredParts.map((p) => p.amount).filter((a): a is number => a !== null);
  const invoicePass =
    amounts.length === 0 || amounts.every((a) => nearlyEqual(a, amounts[0]));

  let invoiceDetail: string | undefined;
  if (!invoicePass) {
    const parts = declaredParts
      .filter((p) => p.amount !== null)
      .map((p) => `${p.label} ${formatMoney(p.amount!)}`);
    invoiceDetail = `Mismatch: ${parts.join(" · ")}`;
  }

  const invoiceDisplay =
    displayCell(grandTotal ?? {}, "final_amount") ||
    displayCell(grandTotal ?? {}, "final_amt") ||
    displayCell(subTotal ?? {}, "final_amt") ||
    displayCell(fuelTotal ?? {}, "final_amt") ||
    (transactions.length ? formatMoney(calculatedInvoice) : "—");

  const billedUnits = [
    ...new Set(transactions.map((t) => displayCell(t, "unit_number")).filter((u) => u.length > 0)),
  ].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  const unitCount = billedUnits.length;
  const missingUnitOnTxn = transactions.some((t) => !displayCell(t, "unit_number"));
  const unitsPass = transactions.length === 0 || (unitCount > 0 && !missingUnitOnTxn);

  const unitsPrimary =
    unitCount === 0 ? "—" : unitCount === 1 ? "1 unit" : `${unitCount} units`;
  const unitsSubvalue = unitCount > 0 ? billedUnits.join(", ") : undefined;

  let unitsDetail: string | undefined;
  if (transactions.length > 0 && missingUnitOnTxn) {
    unitsDetail = "One or more transactions are missing Unit #";
  } else if (unitCount > 0) {
    unitsDetail = `${unitCount} unit${unitCount === 1 ? "" : "s"} billed on this invoice`;
  }

  let cashFromTxns = 0;
  for (const row of transactions) {
    if (displayCell(row, "prod") === "C") {
      cashFromTxns += parseBvdMoneyString(displayCell(row, "final_amt")) ?? 0;
    }
  }

  let cashFromControls = 0;
  for (const row of sorted.filter((r) => r.row_type === "GRAND_TOTAL")) {
    const label = displayCell(row, "row_label");
    const product = displayCell(row, "product");
    if (label === "Manual" || label === "Express" || product === "C" || label === "C") {
      cashFromControls +=
        rowMoney(row, "final_amount", "final_amt") ?? 0;
    }
  }

  const cashTotal = cashFromTxns + cashFromControls;
  const cashGrand = sorted.find(
    (r) =>
      r.row_type === "GRAND_TOTAL" &&
      (displayCell(r, "product") === "C" || displayCell(r, "row_label") === "C"),
  );
  const declaredCash = rowMoney(cashGrand, "final_amount", "final_amt");
  const cashPass = declaredCash === null || nearlyEqual(declaredCash, cashFromTxns);
  const cashDetail =
    cashTotal > 0 || cashFromTxns > 0
      ? `Cash (C) txns ${formatMoney(cashFromTxns)}` +
        (cashFromControls > 0 ? ` · Manual/Express ${formatMoney(cashFromControls)}` : "")
      : "No cash-advance lines on this statement";

  const metrics: BvdValidationMetric[] = [
    {
      id: "invoice_amount",
      label: "Invoice amount",
      value: invoiceDisplay,
      status: amounts.length === 0 ? "na" : invoicePass ? "pass" : "fail",
      detail: invoiceDetail,
    },
    {
      id: "units_processed",
      label: "Units billed",
      value: transactions.length ? unitsPrimary : "—",
      subvalue: transactions.length ? unitsSubvalue : undefined,
      status: transactions.length === 0 ? "na" : unitsPass ? "pass" : "fail",
      detail: unitsDetail,
    },
    {
      id: "cash_advance",
      label: "Cash advance",
      value: transactions.length || cashTotal > 0 ? formatMoney(cashTotal) : "—",
      status:
        transactions.length === 0 && cashTotal === 0
          ? "na"
          : cashPass
            ? "pass"
            : "fail",
      detail: cashDetail,
    },
  ];

  const allPass = metrics.every((m) => m.status === "pass" || m.status === "na");

  return { metrics, allPass };
}
