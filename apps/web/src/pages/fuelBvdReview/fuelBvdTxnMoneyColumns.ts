import type { FuelBvdRow } from "../../api";
import { formatBvdTxnCompactMoney } from "./bvdMoneyDisplay";
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

export { formatBvdTxnCompactMoney } from "./bvdMoneyDisplay";

export function bvdTxnDiscountDisplay(row: FuelBvdRow): string {
  return formatBvdTxnCompactMoney(operationalCell(row, "disc_amt"), { emptyAsZero: true });
}

export function bvdTxnTaxDisplay(row: FuelBvdRow, field: BvdTxnTaxField): string {
  return formatBvdTxnCompactMoney(operationalCell(row, field), { emptyAsZero: true });
}

export function sumBvdTxnMoneyField(transactions: FuelBvdRow[], field: string): number {
  let total = 0;
  for (const row of transactions) {
    const n = parseBvdMoneyString(operationalCell(row, field));
    if (n !== null) total += n;
  }
  return total;
}
