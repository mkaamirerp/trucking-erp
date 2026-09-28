import type { FuelBvdCompletedBasic, FuelBvdImportListItem, FuelReviewQueueItem } from "../../api";

export const FUEL_QUICK_PROVIDER_CODES = ["BVD", "LOVES", "PILOT", "WEX"] as const;

export type FuelDashboardStats = {
  /** Open BVD imports + legacy segment-8 queue items awaiting operator review. */
  needsReviewCount: number;
  processedThisWeekCount: number;
  closingDayLabel: string;
  closingDayIsPlaceholder: boolean;
};

export function computeFuelDashboardStats(
  queue: FuelReviewQueueItem[],
  openBvd: FuelBvdImportListItem[],
  completed: FuelBvdCompletedBasic[],
): FuelDashboardStats {
  const now = Date.now();
  const weekMs = 7 * 24 * 60 * 60 * 1000;
  const processedThisWeek = completed.filter((row) => {
    if (!row.processed_at) return false;
    const t = Date.parse(row.processed_at);
    return Number.isFinite(t) && now - t <= weekMs;
  });

  const pendingBvd = openBvd.filter(
    (r) => r.review_status !== "SOURCE_REVIEWED" && r.review_status !== "IN_REVIEW",
  ).length;
  const inReviewBvd = openBvd.filter((r) => r.review_status === "IN_REVIEW").length;

  return {
    needsReviewCount: queue.length + pendingBvd + inReviewBvd,
    processedThisWeekCount: processedThisWeek.length,
    closingDayLabel: "Sunday",
    closingDayIsPlaceholder: true,
  };
}

export function recentFuelActivity(completed: FuelBvdCompletedBasic[], limit = 5): FuelBvdCompletedBasic[] {
  const sorted = [...completed].sort((a, b) => {
    const ta = a.processed_at ? Date.parse(a.processed_at) : 0;
    const tb = b.processed_at ? Date.parse(b.processed_at) : 0;
    return tb - ta;
  });
  return sorted.slice(0, limit);
}
