import type { FuelBvdCompletedBasic } from "../../api";

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

export function mergeFuelCompletedHistory(
  bvd: FuelBvdCompletedBasic[],
  nationwide: FuelBvdCompletedBasic[],
): FuelBvdCompletedBasic[] {
  const merged = [...bvd, ...nationwide];
  return merged.sort((a, b) => {
    const ta = a.processed_at ? Date.parse(a.processed_at) : 0;
    const tb = b.processed_at ? Date.parse(b.processed_at) : 0;
    return tb - ta;
  });
}

export function recentFuelActivity(completed: FuelBvdCompletedBasic[], limit = 5): FuelBvdCompletedBasic[] {
  const sorted = [...completed].sort((a, b) => {
    const ta = a.processed_at ? Date.parse(a.processed_at) : 0;
    const tb = b.processed_at ? Date.parse(b.processed_at) : 0;
    return tb - ta;
  });
  return sorted.slice(0, limit);
}
