import { useEffect, useState, useCallback } from "react";
import { getDashboardSummary, listDrivers, type DashboardSummary, type Driver } from "../api";

type DashboardState = {
  loading: boolean;
  error?: string;
  summary: DashboardSummary | null;
  drivers: Driver[];
  driversError?: string;
  refetch: () => void;
};

export function useDashboard() {
  const [state, setState] = useState<DashboardState>({
    loading: true,
    summary: null,
    drivers: [],
    refetch: () => {},
  });

  const refetch = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    const errors: string[] = [];
    let summary: DashboardSummary | null = null;
    let drivers: Driver[] = [];

    let driversError: string | undefined;
    try {
      summary = await getDashboardSummary();
      drivers = Array.isArray(summary?.drivers) ? summary.drivers : [];
      // Fallback: if summary has no drivers list but shows drivers on duty, fetch from list endpoint
      if (drivers.length === 0 && (summary?.drivers_active ?? 0) > 0) {
        try {
          const raw = await listDrivers({ limit: 50, include_inactive: true });
          drivers = Array.isArray(raw) ? raw : Array.isArray((raw as { items?: unknown })?.items) ? (raw as { items: Driver[] }).items : [];
        } catch (e: unknown) {
          driversError = e instanceof Error ? e.message : "List request failed";
        }
      }
    } catch (e: unknown) {
      errors.push(`summary: ${e instanceof Error ? e.message : "failed"}`);
    }

    setState({
      loading: false,
      summary,
      drivers,
      driversError,
      error: errors.length ? errors.join(" | ") : undefined,
      refetch,
    });
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { ...state, drivers: state.drivers ?? [], driversError: state.driversError, refetch } as const;
}
