import { describe, expect, it } from "vitest";
import { mapFuelDashboardStatsFromApi, recentFuelActivity } from "./fuelDashboardData";
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
