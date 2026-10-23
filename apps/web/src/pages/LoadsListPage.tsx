import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import StatusBadge from "@/components/StatusBadge";
import {
  discardLoadWorkspaceDraft,
  listBrokers,
  listLoadWorkspaceDrafts,
  listLoads,
  Load,
  type LoadWorkspaceDraft,
} from "@/api";
import {
  loadDraftToListRow,
  workspaceDraftToListRow,
  type DraftListRow,
} from "@/loadWorkspace/draftListPresentation";
import { formatRouteFromStops, firstPickupAppointmentDate } from "@/utils/loadStops";
import { useOperationalRefresh } from "@/core/concurrency/useOperationalRefresh";
import { OPS } from "@/routes";

/** Main loads directory: commercially active rows only (draft loads live under Drafts). */
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
  const [loads, setLoads] = useState<Load[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searchApplied, setSearchApplied] = useState("");
  const [workspaceDrafts, setWorkspaceDrafts] = useState<LoadWorkspaceDraft[]>([]);
  const [draftLoads, setDraftLoads] = useState<Load[]>([]);
  const [brokers, setBrokers] = useState<Awaited<ReturnType<typeof listBrokers>>["items"]>([]);
  const [draftsPanelOpen, setDraftsPanelOpen] = useState(false);

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
      listBrokers({ page: 1, size: 200, sort: "name_asc" }).catch(() => ({ items: [] })),
    ])
      .then(([loadsRes, draftLoadsRes, draftsRes, brokersRes]) => {
        setLoads(loadsRes.items || []);
        setDraftLoads(draftLoadsRes.items || []);
        setWorkspaceDrafts(draftsRes.items || []);
        setBrokers(brokersRes.items || []);
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

  const draftRows: DraftListRow[] = useMemo(() => {
    const brokerList = brokers ?? [];
    const rows = [
      ...workspaceDrafts.map((d) => workspaceDraftToListRow(d, brokerList)),
      ...draftLoads.map((l) => loadDraftToListRow(l, brokerList)),
    ];
    return rows.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  }, [workspaceDrafts, draftLoads, brokers]);

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
        const driver = load.driver ? `${load.driver.first_name} ${load.driver.last_name}`.trim() : "";
        return [
          esc(load.load_number ?? ""),
          esc(load.trip_number?.trim() || ""),
          esc(formatRouteFromStops(load.stops)),
          esc(firstPickupAppointmentDate(load.stops) || ""),
          esc(load.status),
          esc(driver),
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

  async function onDiscardWorkspaceDraft(draftId: string) {
    if (!window.confirm("Discard this draft? Saved data and the PDF will be removed.")) return;
    await discardLoadWorkspaceDraft(draftId, { discard_reason: "operator_discard" });
    runQuery(searchApplied, { silent: true });
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
          {draftRows.length > 0 ? (
            <button
              type="button"
              className={btnClass}
              onClick={() => setDraftsPanelOpen((v) => !v)}
            >
              Drafts ({draftRows.length})
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

      {draftsPanelOpen && draftRows.length > 0 ? (
        <div className="rounded-lg border border-[var(--trk-border)] bg-[#1a1e2a] shadow-sm overflow-hidden">
          <ul className="divide-y divide-[var(--trk-border)]">
            {draftRows.map((row) => (
              <li key={`${row.kind}-${row.id}`} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[var(--trk-text)] truncate">{row.title}</p>
                  {row.missingLine ? (
                    <p className="text-[11px] text-amber-400/90 mt-0.5">{row.missingLine}</p>
                  ) : null}
                  <p className="text-[11px] text-[var(--trk-text-muted)] mt-0.5">
                    {row.pdfHint ? `${row.pdfHint} · ` : ""}
                    Updated {new Date(row.updatedAt).toLocaleString()}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    className={btnClass}
                    onClick={() =>
                      row.kind === "workspace_draft"
                        ? navigate(OPS.LOAD_DRAFT(row.id))
                        : navigate(OPS.LOAD_DETAIL(row.loadId!))
                    }
                  >
                    Open
                  </button>
                  {row.kind === "workspace_draft" ? (
                    <button
                      type="button"
                      className={btnClass}
                      onClick={() => void onDiscardWorkspaceDraft(row.id)}
                    >
                      Discard
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="rounded-lg border border-[var(--trk-border)] bg-[#1a1e2a] shadow-sm overflow-hidden">
        {loading && (
          <p className="px-4 py-6 text-center text-sm text-[var(--trk-text-muted)]">Loading…</p>
        )}
        {error && <p className="px-4 py-6 text-center text-sm text-red-400">{error}</p>}
        {!loading && !error && loads.length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-[var(--trk-text-muted)]">No loads yet.</p>
        )}
        {!loading && !error && loads.length > 0 && (
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
                {loads.map((load) => {
                  const driver = load.driver
                    ? `${load.driver.first_name} ${load.driver.last_name}`.trim()
                    : "";
                  return (
                    <tr
                      key={load.id}
                      className="border-b border-[var(--trk-border)] hover:bg-[var(--trk-surface)] cursor-pointer"
                      onClick={() => navigate(OPS.LOAD_DETAIL(load.id))}
                    >
                      <td className="px-4 py-2.5 text-sm text-[var(--trk-text)]">{load.load_number}</td>
                      <td className="px-4 py-2.5 text-sm text-[var(--trk-text-muted)]">
                        {load.trip_number?.trim() || "—"}
                      </td>
                      <td className="px-4 py-2.5 text-sm text-[var(--trk-text-muted)]">
                        {formatRouteFromStops(load.stops)}
                      </td>
                      <td className="px-4 py-2.5 text-sm text-[var(--trk-text-muted)]">
                        {firstPickupAppointmentDate(load.stops) || "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={load.status} />
                      </td>
                      <td className="px-4 py-2.5 text-sm text-[var(--trk-text-muted)]">{driver || "—"}</td>
                      <td className="px-4 py-2.5 text-right text-sm text-[var(--trk-text)]">
                        {load.rate != null ? String(load.rate) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
