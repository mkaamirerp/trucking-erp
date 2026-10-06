import type { FuelProcessedCurrencyFinancial, FuelProcessedSummary } from "../../api";
import { resolveFuelCurrencyFinancialSummaries } from "./fuelActivityCurrencyFinancial";
import { FUEL_RECENT_ACTIVITY_PREVIEW_LIMIT } from "./fuelDashboardData";

/** Synthetic batch id for the grouped Manual Entry activity row (not a real fuel_source_batches id). */
export const MANUAL_ENTRY_ACTIVITY_GROUP_BATCH_ID = -1;

export type FuelRecentActivityItem =
  | { kind: "batch"; summary: FuelProcessedSummary }
  | { kind: "manual_group"; summary: FuelProcessedSummary; batches: FuelProcessedSummary[] };

function finalizedMs(summary: FuelProcessedSummary): number {
  return summary.finalized_at ? Date.parse(summary.finalized_at) : 0;
}

function parseAmount(raw: string): number | null {
  const trimmed = raw.trim().replace(/,/g, "");
  if (!trimmed) return null;
  const n = Number.parseFloat(trimmed);
  return Number.isFinite(n) ? n : null;
}

function formatAmount(n: number): string {
  const fixed = n.toFixed(4);
  return fixed.replace(/\.?0+$/, "") || "0";
}

function mergeCurrencyFinancialSummaries(
  batches: FuelProcessedSummary[],
): FuelProcessedCurrencyFinancial[] {
  const totals = new Map<string, number>();
  const discounts = new Map<string, number | null>();

  for (const batch of batches) {
    for (const line of resolveFuelCurrencyFinancialSummaries(batch)) {
      const currency = line.currency.trim().toUpperCase();
      const total = parseAmount(line.total_amount);
      if (total !== null) {
        totals.set(currency, (totals.get(currency) ?? 0) + total);
      }
      const prevDiscount = discounts.get(currency);
      if (line.discount_amount == null) {
        discounts.set(currency, null);
      } else if (prevDiscount !== null) {
        const d = parseAmount(line.discount_amount);
        if (d !== null) {
          discounts.set(currency, (prevDiscount ?? 0) + d);
        }
      }
    }
  }

  return [...totals.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([currency, total]) => ({
      currency,
      total_amount: formatAmount(total),
      discount_amount:
        discounts.get(currency) === null || discounts.get(currency) === undefined
          ? null
          : formatAmount(discounts.get(currency) as number),
    }));
}

export function aggregateManualEntrySummaries(batches: FuelProcessedSummary[]): FuelProcessedSummary {
  const sorted = [...batches].sort((a, b) => finalizedMs(b) - finalizedMs(a));
  const latest = sorted[0]!;
  const currencyFinancialSummaries = mergeCurrencyFinancialSummaries(sorted);
  const transactionCount = sorted.reduce((n, b) => n + (b.transaction_count ?? 0), 0);
  const controlCount = sorted.reduce((n, b) => n + (b.control_count ?? 0), 0);
  const count = sorted.length;

  return {
    batch_id: MANUAL_ENTRY_ACTIVITY_GROUP_BATCH_ID,
    provider_code: "MANUAL_ENTRY",
    source_import_ref: null,
    source_storage_ref: null,
    account_reference: null,
    invoice_number: count === 1 ? latest.invoice_number : `${count} entries`,
    period_start: sorted.map((b) => b.period_start).filter(Boolean).sort()[0] ?? null,
    period_end: sorted.map((b) => b.period_end).filter(Boolean).sort().at(-1) ?? null,
    due_date: null,
    finalized_at: latest.finalized_at,
    batch_status: latest.batch_status,
    transaction_count: transactionCount,
    control_count: controlCount,
    currency_totals: [],
    currency_financial_summaries: currencyFinancialSummaries,
    provider_control_totals: [],
    cad_transaction_total: null,
    usd_transaction_total: null,
    usd_provider_control: null,
    purchase_card_count: 0,
    purchase_card_numbers: [],
    total_amount: currencyFinancialSummaries.length === 1 ? currencyFinancialSummaries[0].total_amount : "",
    currency: currencyFinancialSummaries.length === 1 ? currencyFinancialSummaries[0].currency : null,
    read_only: true,
    review_status: latest.review_status,
  };
}

/**
 * One table row per non-manual batch; all manual batches collapse into a single Manual Entry row.
 * Expand that row to show every manual batch workspace.
 */
export function buildFuelRecentActivityDisplay(
  completed: FuelProcessedSummary[],
  limit = FUEL_RECENT_ACTIVITY_PREVIEW_LIMIT,
): FuelRecentActivityItem[] {
  const sorted = [...completed].sort((a, b) => finalizedMs(b) - finalizedMs(a));
  const manual: FuelProcessedSummary[] = [];
  const other: FuelProcessedSummary[] = [];
  for (const summary of sorted) {
    if (summary.provider_code === "MANUAL_ENTRY") {
      manual.push(summary);
    } else {
      other.push(summary);
    }
  }

  const dated: { at: number; item: FuelRecentActivityItem }[] = other.map((summary) => ({
    at: finalizedMs(summary),
    item: { kind: "batch", summary },
  }));

  if (manual.length > 0) {
    const batches = [...manual].sort((a, b) => finalizedMs(b) - finalizedMs(a));
    dated.push({
      at: finalizedMs(batches[0]!),
      item: {
        kind: "manual_group",
        summary: aggregateManualEntrySummaries(batches),
        batches,
      },
    });
  }

  dated.sort((a, b) => b.at - a.at);
  return dated.slice(0, limit).map((row) => row.item);
}

export function isManualEntryActivityGroupBatchId(batchId: number): boolean {
  return batchId === MANUAL_ENTRY_ACTIVITY_GROUP_BATCH_ID;
}
