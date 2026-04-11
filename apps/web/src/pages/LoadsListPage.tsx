import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import StatusBadge from "@/components/StatusBadge";
import { listLoads, Load } from "@/api";
import { formatRouteFromStops, firstPickupAppointmentDate } from "@/utils/loadStops";
import { useOperationalRefresh } from "@/core/concurrency/useOperationalRefresh";
import { OPS } from "@/routes";

export default function LoadsListPage() {
  const navigate = useNavigate();
  const [loads, setLoads] = useState<Load[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searchApplied, setSearchApplied] = useState("");

  const runQuery = useCallback((q: string, opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false;
    if (!silent) setLoading(true);
    setError(null);
    listLoads({ page: 1, size: 50, search: q || undefined })
      .then((res) => setLoads(res.items || []))
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
    "rounded-md border border-[#252a38] bg-[#1e2330] px-3 py-1.5 text-[11px] font-semibold text-[#7a8299] hover:border-[#3a4155] hover:bg-[#252a38] disabled:opacity-50";

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#e8ecf4]">Loads</h1>
          <p className="text-[11px] text-[#7a8299]">Manage loads and dispatch.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applySearch()}
            placeholder="Search load #, trip #, broker ref…"
            className="min-w-[200px] rounded-md border border-[#252a38] bg-[#1a1e2a] px-3 py-1.5 text-sm text-[#e8ecf4] placeholder:text-[#4a5068] focus:border-amber-500 focus:outline-none"
          />
          <button type="button" className={btnClass} onClick={applySearch} disabled={loading}>
            Search
          </button>
          {searchApplied ? (
            <button
              type="button"
              className={btnClass}
              onClick={() => { setSearchInput(""); setSearchApplied(""); runQuery(""); }}
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
          <button
            type="button"
            className="rounded-md bg-amber-500 px-3 py-1.5 text-[11px] font-semibold text-slate-900 hover:bg-amber-400"
            onClick={() => navigate(OPS.LOAD_NEW)}
          >
            + New load
          </button>
        </div>
      </div>

      {/* Table card */}
      <div className="rounded-lg border border-[#252a38] bg-[#1a1e2a] shadow-sm overflow-hidden">
        {loading && (
          <p className="px-4 py-6 text-center text-sm text-[#7a8299]">Loading…</p>
        )}
        {error && (
          <p className="px-4 py-6 text-center text-sm text-red-400">{error}</p>
        )}
        {!loading && !error && loads.length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-[#7a8299]">No loads yet.</p>
        )}
        {!loading && !error && loads.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-[#252a38] bg-[#1e2330]">
                  {["Load #", "Trip #", "Route", "First pickup", "Status", "Driver", "Rate"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wide text-[#4a5068]"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loads.map((load) => (
                  <tr
                    key={load.id}
                    className="border-b border-[#252a38] last:border-0 cursor-pointer hover:bg-[#1e2330] transition-colors"
                    onClick={() => navigate(OPS.LOAD_DETAIL(load.id))}
                  >
                    <td className="px-4 py-2.5 text-sm font-medium text-[#e8ecf4]">
                      {load.load_number || <span className="text-[#4a5068]">—</span>}
                    </td>
                    <td className="px-4 py-2.5 text-sm text-[#7a8299]">
                      {load.trip_number?.trim() || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-sm text-[#7a8299] max-w-[220px] truncate">
                      {formatRouteFromStops(load.stops) || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-sm text-[#7a8299]">
                      {firstPickupAppointmentDate(load.stops) || "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <StatusBadge status={load.status} />
                    </td>
                    <td className="px-4 py-2.5 text-sm text-[#7a8299]">
                      {load.driver ? `${load.driver.first_name} ${load.driver.last_name}` : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-sm text-[#7a8299]">
                      {load.rate != null ? `$${load.rate}` : "—"}
                    </td>
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
