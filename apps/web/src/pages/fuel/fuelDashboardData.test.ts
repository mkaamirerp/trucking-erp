import { describe, expect, it } from "vitest";
import { mapFuelDashboardStatsFromApi, recentFuelProcessedActivity } from "./fuelDashboardData";
import type { FuelProcessedSummary } from "../../api";

function sampleProcessed(batchId: number, finalizedAt: string): FuelProcessedSummary {
  return {
    batch_id: batchId,
    provider_code: "BVD",
    source_import_ref: `import-${batchId}`,
    source_storage_ref: null,
    account_reference: null,
    invoice_number: String(972200 + batchId),
    period_start: null,
    period_end: null,
    due_date: null,
    finalized_at: finalizedAt,
    batch_status: "FINALIZED",
    transaction_count: 1,
    control_count: 0,
    currency_totals: [],
    currency_financial_summaries: [{ currency: "CAD", total_amount: "1.00", discount_amount: "0" }],
    provider_control_totals: [],
    cad_transaction_total: null,
    usd_transaction_total: null,
    usd_provider_control: null,
    purchase_card_count: 0,
    purchase_card_numbers: [],
    total_amount: "1.00",
    currency: "CAD",
    read_only: true,
    review_status: "SOURCE_REVIEWED",
  };
}

describe("fuelDashboardData", () => {
  it("returns up to ten recent processed batches by default", () => {
    const rows = Array.from({ length: 12 }, (_, i) =>
      sampleProcessed(i, new Date(2026, 0, i + 1).toISOString()),
    );
    expect(recentFuelProcessedActivity(rows)).toHaveLength(10);
    expect(recentFuelProcessedActivity(rows, 5)).toHaveLength(5);
  });

  it("maps dashboard stats from API shape", () => {
    expect(
      mapFuelDashboardStatsFromApi({
        needs_review_count: 2,
        processed_last_7_days_count: 5,
      }),
    ).toEqual({
      needsReviewCount: 2,
      processedLast7DaysCount: 5,
    });
  });
});
