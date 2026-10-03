import type { FuelBvdRow } from "../../api";
import { operationalCell } from "../fuelBvdReview/bvdParsedDisplay";
import { parseBvdMoneyString } from "../fuelBvdReview/bvdParsedValidation";

/** Distinct non-empty `cur` tokens on charge rows (legacy fallback when summaries missing). */
export function distinctProcessedChargeCurrencies(rows: FuelBvdRow[]): string[] {
  const codes = new Set<string>();
  for (const row of rows) {
    const raw = operationalCell(row, "cur").trim().toUpperCase();
    if (raw) codes.add(raw);
  }
  return [...codes].sort();
}

export function sumProcessedChargeFinalAmount(rows: FuelBvdRow[]): number {
  let total = 0;
  for (const row of rows) {
    const n = parseBvdMoneyString(operationalCell(row, "final_amt"));
    if (n !== null) total += n;
  }
  return total;
}

export function formatProcessedMoneyTotal(amount: number): string {
  return amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
