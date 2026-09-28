import { describe, expect, it } from "vitest";
import { computeFuelDashboardStats, recentFuelActivity } from "./fuelDashboardData";
import type { FuelBvdCompletedBasic } from "../../api";

describe("fuelDashboardData", () => {
  it("returns up to five recent completed items", () => {
    const rows: FuelBvdCompletedBasic[] = Array.from({ length: 8 }, (_, i) => ({
      provider: "BVD",
      import_id: `id-${i}`,
      invoice_number: String(972200 + i),
      review_status: "SOURCE_REVIEWED",
      read_only: true,
      unit_count: 1,
      unit_numbers: [],
      total_amount: "1.00",
      categories: [],
      taxes: [],
      processed_at: new Date(2026, 0, i + 1).toISOString(),
    }));
    expect(recentFuelActivity(rows, 5)).toHaveLength(5);
  });

  it("computes stats from queue and imports", () => {
    const stats = computeFuelDashboardStats(
      [{ batch_id: 1 } as never],
      [{ import_id: "a", invoice_number: "1", review_status: "IN_REVIEW" }],
      [],
    );
    expect(stats.needsReviewCount).toBeGreaterThan(0);
    expect(stats.closingDayIsPlaceholder).toBe(true);
  });
});
