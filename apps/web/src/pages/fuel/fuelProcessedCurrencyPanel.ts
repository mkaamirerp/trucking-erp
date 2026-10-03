import type { FuelBvdRow, FuelCanonicalTransaction, FuelProcessedCurrencyTotal } from "../../api";
import { operationalCell } from "../fuelBvdReview/bvdParsedDisplay";
import type { FuelCurrencyFinancialLine } from "./fuelActivityCurrencyFinancial";
import { formatProviderMoneyAmount } from "./fuelProviderMoneyDisplay";

function legacyRowCurrencyCode(raw: string): string {
  const u = raw.trim().toUpperCase();
  if (u === "US") return "USD";
  if (u === "CN") return "CAD";
  return u;
}

/** Per-currency transaction counts from canonical read (preferred) or card charge rows. */
export function countFuelTransactionsByCurrency(
  currencyLines: FuelCurrencyFinancialLine[],
  canonicalTransactions: FuelCanonicalTransaction[],
  cardTransactionRows: FuelBvdRow[],
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const line of currencyLines) {
    counts[line.currency] = 0;
  }
  if (canonicalTransactions.length > 0) {
    for (const txn of canonicalTransactions) {
      const code = (txn.currency || "").trim().toUpperCase();
      if (!code) continue;
      counts[code] = (counts[code] ?? 0) + 1;
    }
    return counts;
  }
  for (const row of cardTransactionRows) {
    const code = legacyRowCurrencyCode(operationalCell(row, "cur"));
    if (!code) continue;
    counts[code] = (counts[code] ?? 0) + 1;
  }
  return counts;
}

function parseMoney(raw: string): number | null {
  const trimmed = raw.trim().replace(/,/g, "");
  if (!trimmed) return null;
  const n = Number.parseFloat(trimmed);
  return Number.isFinite(n) ? n : null;
}

/** e.g. `0.02 under provider total` when processed total is below provider control. */
export function providerControlVarianceLabel(
  currency: string,
  processedTotalAmount: string,
  providerControlTotals: FuelProcessedCurrencyTotal[],
): string | null {
  const code = currency.trim().toUpperCase();
  const control = providerControlTotals.find((row) => row.currency.trim().toUpperCase() === code);
  if (!control) return null;
  const processed = parseMoney(processedTotalAmount);
  const provider = parseMoney(control.amount);
  if (processed === null || provider === null) return null;
  const delta = provider - processed;
  if (Math.abs(delta) < 0.000_05) return null;
  const magnitude = Math.abs(delta).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
  if (delta > 0) return `${magnitude} under provider total`;
  return `${magnitude} over provider total`;
}

export function formatProcessedPanelMoney(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "—";
  const parsed = parseMoney(trimmed);
  if (parsed !== null) {
    return parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  }
  return formatProviderMoneyAmount(trimmed, { emptyAsZero: true });
}
