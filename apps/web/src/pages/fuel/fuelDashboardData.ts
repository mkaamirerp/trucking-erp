import type { FuelProcessedSummary } from "../../api";

export const FUEL_QUICK_PROVIDER_CODES = ["BVD", "LOVES", "PILOT", "WEX"] as const;

export type FuelDashboardStats = {
  needsReviewCount: number;
  processedLast7DaysCount: number;
};

export function mapFuelDashboardStatsFromApi(stats: {
  needs_review_count: number;
  processed_last_7_days_count: number;
}): FuelDashboardStats {
  return {
    needsReviewCount: stats.needs_review_count,
    processedLast7DaysCount: stats.processed_last_7_days_count,
  };
}

export function recentFuelProcessedActivity(
  completed: FuelProcessedSummary[],
  limit = 5,
): FuelProcessedSummary[] {
  const sorted = [...completed].sort((a, b) => {
    const ta = a.finalized_at ? Date.parse(a.finalized_at) : 0;
    const tb = b.finalized_at ? Date.parse(b.finalized_at) : 0;
    return tb - ta;
  });
  return sorted.slice(0, limit);
}
