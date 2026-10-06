import { describe, expect, it } from "vitest";
import type { FuelProcessedSummary } from "../../api";
import {
  MANUAL_ENTRY_ACTIVITY_GROUP_BATCH_ID,
  aggregateManualEntrySummaries,
  buildFuelRecentActivityDisplay,
} from "./fuelRecentActivityDisplay";

function manualBatch(id: number, finalizedAt: string, total: string, currency: string): FuelProcessedSummary {
  return {
    batch_id: id,
    provider_code: "MANUAL_ENTRY",
    source_import_ref: `stage-${id}`,
    source_storage_ref: null,
    account_reference: null,
    invoice_number: id === 12 ? "41868" : "—",
    period_start: null,
    period_end: null,
    due_date: null,
    finalized_at: finalizedAt,
    batch_status: "FINALIZED",
    transaction_count: 1,
    control_count: 0,
    currency_totals: [],
    currency_financial_summaries: [
      { currency, total_amount: total, discount_amount: "0.00" },
    ],
    provider_control_totals: [],
    cad_transaction_total: null,
    usd_transaction_total: null,
    usd_provider_control: null,
    purchase_card_count: 0,
    purchase_card_numbers: [],
    total_amount: total,
    currency,
    read_only: true,
    review_status: "SOURCE_REVIEWED",
  };
}

describe("buildFuelRecentActivityDisplay", () => {
  it("collapses manual batches into one row with combined totals", () => {
    const bvd: FuelProcessedSummary = {
      ...manualBatch(1, "2026-01-01T00:00:00Z", "10", "USD"),
      provider_code: "BVD",
      invoice_number: "838710",
    };
    const manual = [
      manualBatch(12, "2026-02-01T00:00:00Z", "1050.02", "USD"),
      manualBatch(13, "2026-01-15T00:00:00Z", "500", "CAD"),
    ];
    const items = buildFuelRecentActivityDisplay([...manual, bvd], 10);
    expect(items).toHaveLength(2);
    const group = items.find((i) => i.kind === "manual_group");
    expect(group).toBeTruthy();
    if (group?.kind !== "manual_group") return;
    expect(group.batches).toHaveLength(2);
    expect(group.summary.batch_id).toBe(MANUAL_ENTRY_ACTIVITY_GROUP_BATCH_ID);
    expect(group.summary.invoice_number).toBe("2 entries");
    expect(group.summary.transaction_count).toBe(2);
    const usd = group.summary.currency_financial_summaries.find((l) => l.currency === "USD");
    expect(usd?.total_amount).toBe("1050.02");
  });
});

describe("aggregateManualEntrySummaries", () => {
  it("uses single invoice label when only one manual batch", () => {
    const one = manualBatch(12, "2026-02-01T00:00:00Z", "1050.02", "USD");
    const agg = aggregateManualEntrySummaries([one]);
    expect(agg.invoice_number).toBe("41868");
  });
});
