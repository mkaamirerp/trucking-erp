import type { FuelProcessedCurrencyFinancial, FuelProcessedSummary } from "../../api";
import { formatProviderMoneyAmount } from "./fuelProviderMoneyDisplay";
import { formatProcessedMoneyTotal } from "./processedStatementMoney";

export type FuelCurrencyFinancialLine = {
  currency: string;
  total_amount: string;
  discount_amount: string | null;
};

/** Canonical per-currency money lines (no FX). Legacy fallback: totals only, discount unknown. */
export function resolveFuelCurrencyFinancialSummaries(
  summary: Pick<FuelProcessedSummary, "currency_financial_summaries" | "currency_totals">,
): FuelCurrencyFinancialLine[] {
  const fromCanonical = summary.currency_financial_summaries ?? [];
  if (fromCanonical.length > 0) {
    return fromCanonical.map((line) => ({
      currency: line.currency.trim(),
      total_amount: line.total_amount,
      discount_amount: line.discount_amount ?? null,
    }));
  }
  return (summary.currency_totals ?? []).map((line) => ({
    currency: line.currency.trim(),
    total_amount: line.amount,
    discount_amount: null,
  }));
}

export function formatFuelCurrencyFinancialDiscount(line: FuelCurrencyFinancialLine): string {
  return formatProviderMoneyAmount(line.discount_amount, { emptyAsZero: true });
}

export function formatFuelCurrencyFinancialTotal(line: FuelCurrencyFinancialLine): string {
  const amt = formatProviderMoneyAmount(line.total_amount, { emptyAsZero: true });
  return `${amt} ${line.currency}`;
}

/** One summary row: `USD · Discount 120.50 · Total 5,197.67 USD` */
export function formatFuelActivityStatementCurrencyLine(line: FuelCurrencyFinancialLine): string {
  return `${line.currency} · Discount ${formatFuelCurrencyFinancialDiscount(line)} · Total ${formatFuelCurrencyFinancialTotal(line)}`;
}

/** Invoice-total column / processed header: dynamic currency list, never mixed. */
export function formatFuelActivityInvoiceTotalFromCurrencySummaries(
  lines: FuelCurrencyFinancialLine[],
): string {
  if (lines.length === 0) return "—";
  return lines.map((line) => formatFuelCurrencyFinancialTotal(line)).join(" · ");
}

export function fuelCurrencyFinancialFromApi(
  lines: FuelProcessedCurrencyFinancial[] | undefined,
): FuelCurrencyFinancialLine[] {
  if (!lines?.length) return [];
  return lines.map((line) => ({
    currency: line.currency.trim(),
    total_amount: line.total_amount,
    discount_amount: line.discount_amount,
  }));
}

/**
 * Processed statement section header amount (e.g. Fuel / Card Transactions).
 * Never returns a single number that mixes unlike currencies.
 */
export function processedSectionSummaryAmount(
  currencyLines: FuelCurrencyFinancialLine[],
  legacySummedAmount: number,
  distinctLegacyCurrencyCodes: string[],
): string | null {
  if (currencyLines.length > 1) {
    return null;
  }
  if (currencyLines.length === 1) {
    return formatFuelCurrencyFinancialTotal(currencyLines[0]);
  }
  if (distinctLegacyCurrencyCodes.length > 1) {
    return null;
  }
  if (distinctLegacyCurrencyCodes.length === 1) {
    return `${formatProcessedMoneyTotal(legacySummedAmount)} ${distinctLegacyCurrencyCodes[0]}`;
  }
  return formatProcessedMoneyTotal(legacySummedAmount);
}
