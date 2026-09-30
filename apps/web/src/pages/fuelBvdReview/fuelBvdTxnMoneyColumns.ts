import type { FuelBvdRow } from "../../api";
import { formatMoneyDisplay } from "./bvdCompletedBasicProjection";
import { operationalCell } from "./bvdParsedDisplay";
import { parseBvdMoneyString } from "./bvdParsedValidation";
import { isNonZeroMoney } from "./bvdTransactionRowPresentation";

export type BvdTxnTaxField = "hst" | "gst" | "pst" | "qst";

export type BvdTxnActiveTaxColumn = {
  field: BvdTxnTaxField;
  label: string;
};

export const BVD_TXN_TAX_SPECS: readonly BvdTxnActiveTaxColumn[] = [
  { field: "hst", label: "HST" },
  { field: "gst", label: "GST" },
  { field: "pst", label: "PST" },
  { field: "qst", label: "QST" },
];

/** Tax columns visible for this invoice's displayed transaction set. */
export function activeBvdTxnTaxColumns(transactions: FuelBvdRow[]): BvdTxnActiveTaxColumn[] {
  return BVD_TXN_TAX_SPECS.filter(({ field }) =>
    transactions.some((row) => isNonZeroMoney(operationalCell(row, field))),
  );
}

/** Compact table money cell — known zero → 0.00; missing → —; else formatted source. */
export function formatBvdTxnCompactMoney(raw: string): string {
  const t = raw.trim();
  if (!t) return "—";
  const formatted = formatMoneyDisplay(t);
  if (formatted) return formatted;
  const n = parseBvdMoneyString(t);
  if (n !== null) {
    return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return t;
}

export function bvdTxnDiscountDisplay(row: FuelBvdRow): string {
  return formatBvdTxnCompactMoney(operationalCell(row, "disc_amt"));
}

export function bvdTxnTaxDisplay(row: FuelBvdRow, field: BvdTxnTaxField): string {
  return formatBvdTxnCompactMoney(operationalCell(row, field));
}

export function sumBvdTxnMoneyField(transactions: FuelBvdRow[], field: string): number {
  let total = 0;
  for (const row of transactions) {
    const n = parseBvdMoneyString(operationalCell(row, field));
    if (n !== null) total += n;
  }
  return total;
}
