import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import OperatorLoadStatusChip from "@/components/OperatorLoadStatusChip";
import {
  devPlaygroundResetLoadsAndTrips,
  listLoadWorkspaceDrafts,
  listLoads,
  Load,
  type LoadWorkspaceDraft,
} from "@/api";
import { isTenantAdmin } from "@/auth/roles";
import { useMe } from "@/hooks/useMe";
import { getTenantSlugFromHost } from "@/tenant";
import { associatedTripDriverLabel, associatedTripNumber, buildLoadsDirectoryRows } from "@/loadWorkspace/draftListPresentation";
import { formatRouteFromStops, firstPickupAppointmentDate } from "@/utils/loadStops";
import { useOperationalRefresh } from "@/core/concurrency/useOperationalRefresh";
import { OPS } from "@/routes";

/** Main loads directory: active loads plus rows in status draft (saved-for-later and legacy load drafts). */
const LOAD_LIST_DEFAULT_STATUSES = [
  "ready",
  "unassigned",
  "assigned",
  "dispatched",
  "arrived_pickup",
  "in_transit",
  "arrived_delivery",
  "delivered",
  "issue_hold",
];

export default function LoadsListPage() {
  const navigate = useNavigate();
  const { me } = useMe();
  const demoSlug =
    getTenantSlugFromHost() === "demo" ||
    (me?.tenant_slug ?? "").trim().toLowerCase() === "demo";
  const showDemoReset = demoSlug && isTenantAdmin(me?.roles);
  const [loads, setLoads] = useState<Load[]>([]);
  const [resetBusy, setResetBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searchApplied, setSearchApplied] = useState("");
  const [workspaceDrafts, setWorkspaceDrafts] = useState<LoadWorkspaceDraft[]>([]);
  const [draftLoads, setDraftLoads] = useState<Load[]>([]);
  const runQuery = useCallback((q: string, opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false;
    if (!silent) setLoading(true);
    setError(null);
    Promise.all([
      listLoads({
        page: 1,
        size: 50,
        search: q || undefined,
        status: LOAD_LIST_DEFAULT_STATUSES,
      }),
      listLoads({ page: 1, size: 20, status: ["draft"], search: q || undefined }),
      listLoadWorkspaceDrafts({ status: "draft", page: 1, size: 20 }).catch(() => ({
        items: [] as LoadWorkspaceDraft[],
        total: 0,
        page: 1,
        size: 20,
      })),
    ])
      .then(([loadsRes, draftLoadsRes, draftsRes]) => {
        setLoads(loadsRes.items || []);
        setDraftLoads(draftLoadsRes.items || []);
        setWorkspaceDrafts(draftsRes.items || []);
      })
      .catch((e) => {
        if (!silent) setError(e?.message || "Failed to load loads");
      })
      .finally(() => {
        if (!silent) setLoading(false);
      });
  }, []);

  useEffect(() => {
    runQuery("");
  }, [runQuery]);

  useOperationalRefresh({
    intervalMs: 30_000,
    onRefresh: () => runQuery(searchApplied, { silent: true }),
  });

  const directoryRows = useMemo(
    () =>
      buildLoadsDirectoryRows(loads, draftLoads, workspaceDrafts, searchApplied),
    [loads, draftLoads, workspaceDrafts, searchApplied],
  );

  const applySearch = () => {
    const q = searchInput.trim();
    setSearchApplied(q);
    runQuery(q, { silent: false });
  };

  const exportCsv = () => {
    const headers = ["load_number", "trip_number", "route", "first_pickup_date", "status", "driver", "rate"];
    const esc = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const lines = [
      headers.join(","),
      ...loads.map((load) => {
        return [
          esc(load.load_number ?? ""),
          esc(associatedTripNumber(load)),
          esc(formatRouteFromStops(load.stops)),
          esc(firstPickupAppointmentDate(load.stops) || ""),
          esc(load.status),
          esc(associatedTripDriverLabel(load)),
          load.rate != null ? String(load.rate) : "",
        ].join(",");
      }),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `loads-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const btnClass =
    "rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-text-muted)] hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)] disabled:opacity-50";

  async function onDemoResetLoadsAndTrips() {
    if (
      !window.confirm(
        "Delete ALL loads, trips, workspace drafts, and related operational data for the demo tenant? Trip numbers will restart from your locked prefix + 10001. This cannot be undone.",
      )
    ) {
      return;
    }
    if (
      !window.confirm(
        "Last chance: confirm demo reset. Fuel, payroll, drivers, and brokers are NOT deleted.",
      )
    ) {
      return;
    }
    setResetBusy(true);
    setError(null);
    try {
      const out = await devPlaygroundResetLoadsAndTrips();
      window.alert(out.message || "Reset complete.");
      runQuery("", { silent: false });
    } catch (e: unknown) {
      setError((e as Error)?.message || "Demo reset failed");
    } finally {
      setResetBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[var(--trk-text)]">Loads</h1>
          <p className="text-[11px] text-[var(--trk-text-muted)]">Manage loads and dispatch.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applySearch()}
            placeholder="Search load #, trip #, broker ref…"
            className="min-w-[200px] rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-sm text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)] focus:border-amber-500 focus:outline-none"
          />
          <button type="button" className={btnClass} onClick={applySearch} disabled={loading}>
            Search
          </button>
          {searchApplied ? (
            <button
              type="button"
              className={btnClass}
              onClick={() => {
                setSearchInput("");
                setSearchApplied("");
                runQuery("");
              }}
              disabled={loading}
            >
              Clear
            </button>
          ) : null}
          {!loading && loads.length > 0 ? (
            <button type="button" className={btnClass} onClick={exportCsv}>
              Export CSV
            </button>
          ) : null}
          {showDemoReset ? (
            <button
              type="button"
              className={`${btnClass} border-red-500/40 text-red-700 hover:border-red-500`}
              onClick={() => void onDemoResetLoadsAndTrips()}
              disabled={loading || resetBusy}
              title="Demo only: wipe loads/trips and reset trip numbering"
            >
              {resetBusy ? "Resetting…" : "Reset loads & trips (demo)"}
            </button>
          ) : null}
          <button
            type="button"
            className="rounded-md bg-amber-500 px-3 py-1.5 text-[11px] font-semibold text-slate-900 hover:bg-amber-400"
            onClick={() => navigate(OPS.LOAD_NEW)}
          >
            + New load
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--trk-border)] bg-[#1a1e2a] shadow-sm overflow-hidden">
        {loading && (
          <p className="px-4 py-6 text-center text-sm text-[var(--trk-text-muted)]">Loading…</p>
        )}
        {error && <p className="px-4 py-6 text-center text-sm text-red-400">{error}</p>}
        {!loading && !error && directoryRows.length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-[var(--trk-text-muted)]">No loads yet.</p>
        )}
        {!loading && !error && directoryRows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-[var(--trk-border)] bg-[var(--trk-surface)]">
                  <th className="px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                    Load #
                  </th>
                  <th className="px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                    Trip #
                  </th>
                  <th className="px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                    Route
                  </th>
                  <th className="px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                    Pickup
                  </th>
                  <th className="px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                    Status
                  </th>
                  <th className="px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                    Driver
                  </th>
                  <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                    Rate
                  </th>
                </tr>
              </thead>
              <tbody>
                {directoryRows.map((row) => (
                  <tr
                    key={row.key}
                    className="border-b border-[var(--trk-border)] hover:bg-[var(--trk-surface)] cursor-pointer"
                    onClick={() =>
                      row.kind === "workspace_draft" && row.workspaceDraftId
                        ? navigate(OPS.LOAD_DRAFT(row.workspaceDraftId))
                        : row.loadId != null
                          ? navigate(OPS.LOAD_DETAIL(row.loadId))
                          : undefined
                    }
                  >
                    <td className="px-4 py-2.5 text-sm text-[var(--trk-text)]">{row.loadNumber}</td>
                    <td className="px-4 py-2.5 text-sm text-[var(--trk-text-muted)]">{row.tripNumber}</td>
                    <td className="px-4 py-2.5 text-sm text-[var(--trk-text-muted)]">{row.route}</td>
                    <td className="px-4 py-2.5 text-sm text-[var(--trk-text-muted)]">{row.pickup}</td>
                    <td className="px-4 py-2.5">
                      <OperatorLoadStatusChip load={row.operatorStatus} />
                    </td>
                    <td className="px-4 py-2.5 text-sm text-[var(--trk-text-muted)]">{row.driver}</td>
                    <td className="px-4 py-2.5 text-right text-sm text-[var(--trk-text)]">{row.rateDisplay}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
