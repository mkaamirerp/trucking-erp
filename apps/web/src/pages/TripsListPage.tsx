import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import StatusBadge from "@/components/StatusBadge";
import { listTrips, type TripListItem } from "@/api";
import { useOperationalRefresh } from "@/core/concurrency/useOperationalRefresh";
import { OPS } from "@/routes";

export default function TripsListPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<TripListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searchApplied, setSearchApplied] = useState("");
  const [statusInput, setStatusInput] = useState("");
  const [statusApplied, setStatusApplied] = useState("");

  const runQuery = useCallback(
    (q: string, status: string, opts?: { silent?: boolean }) => {
      const silent = opts?.silent ?? false;
      if (!silent) setLoading(true);
      setError(null);
      listTrips({
        page: 1,
        size: 50,
        search: q || undefined,
        status: status.trim() || undefined,
      })
        .then((res) => {
          setItems(res.items || []);
          setTotal(res.total ?? 0);
        })
        .catch((e: Error) => {
          if (!silent) setError(e?.message || "Failed to load trips");
        })
        .finally(() => {
          if (!silent) setLoading(false);
        });
    },
    [],
  );

  useEffect(() => {
    runQuery("", "");
  }, [runQuery]);

  useOperationalRefresh({
    intervalMs: 30_000,
    onRefresh: () => runQuery(searchApplied, statusApplied, { silent: true }),
  });

  const applyFilters = () => {
    const q = searchInput.trim();
    const st = statusInput.trim();
    setSearchApplied(q);
    setStatusApplied(st);
    runQuery(q, st, { silent: false });
  };

  const btnClass =
    "rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-text-muted)] hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)] disabled:opacity-50";

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[var(--trk-text)]">Trips</h1>
          <p className="text-[11px] text-[var(--trk-text-muted)]">
            Operational trip containers. Open a trip for member loads; load pages stay the commercial workspace.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyFilters()}
            placeholder="Trip #, load #, broker…"
            className="min-w-[200px] rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-sm text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)] focus:border-amber-500 focus:outline-none"
          />
          <input
            type="text"
            value={statusInput}
            onChange={(e) => setStatusInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyFilters()}
            placeholder="Status (exact)"
            className="w-[140px] rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-sm text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)] focus:border-amber-500 focus:outline-none"
          />
          <button type="button" className={btnClass} onClick={applyFilters} disabled={loading}>
            Apply
          </button>
          {(searchApplied || statusApplied) ? (
            <button
              type="button"
              className={btnClass}
              onClick={() => {
                setSearchInput("");
                setSearchApplied("");
                setStatusInput("");
                setStatusApplied("");
                runQuery("", "");
              }}
            >
              Clear
            </button>
          ) : null}
        </div>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      {loading ? (
        <p className="text-sm text-[var(--trk-text-muted)]">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)]">
          <table className="min-w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--trk-border)] bg-[var(--trk-bg)] text-[11px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                <th className="px-4 py-2.5">Trip</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Cancelled</th>
                <th className="px-4 py-2.5">Loads</th>
                <th className="px-4 py-2.5">First load / route</th>
                <th className="px-4 py-2.5">Driver / equipment</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr
                  key={t.id}
                  className="cursor-pointer border-b border-[var(--trk-border)] last:border-0 hover:bg-[var(--trk-bg)]"
                  onClick={() => navigate(OPS.TRIP_DETAIL(t.id))}
                >
                  <td className="px-4 py-3">
                    <Link
                      to={OPS.TRIP_DETAIL(t.id)}
                      className="font-medium text-[var(--trk-heading)] hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t.trip_number}
                    </Link>
                    <div className="text-[11px] text-[var(--trk-text-muted)]">{t.job_type}</div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="px-4 py-3 text-[12px] text-[var(--trk-text-muted)]">
                    {t.cancelled_at ? (
                      <span className="text-red-700/90">{new Date(t.cancelled_at).toLocaleString()}</span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-[12px]">{t.member_load_count}</td>
                  <td className="max-w-[280px] px-4 py-3 text-[12px] text-[var(--trk-text-muted)]">
                    {t.first_member ? (
                      <>
                        <div className="font-medium text-[var(--trk-text)]">{t.first_member.load_number}</div>
                        <div className="truncate">
                          {t.first_member.broker_name_snapshot || "—"}
                          {t.first_member.broker_load_reference ? ` · ${t.first_member.broker_load_reference}` : ""}
                        </div>
                        {t.first_member.stop_route_summary ? (
                          <div className="mt-0.5 truncate text-[11px]">{t.first_member.stop_route_summary}</div>
                        ) : null}
                      </>
                    ) : (
                      <span className="italic">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[12px] text-[var(--trk-text-muted)]">
                    {t.driver ? `${t.driver.first_name} ${t.driver.last_name}` : "—"}
                    <div className="text-[11px]">
                      {t.truck ? `Truck ${t.truck.unit_number}` : ""}
                      {t.truck && t.trailer ? " · " : ""}
                      {t.trailer ? `Trl ${t.trailer.unit_number}` : ""}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-[var(--trk-text-muted)]">No trips match your filters.</p>
          ) : null}
        </div>
      )}

      {!loading && items.length > 0 ? (
        <p className="text-[11px] text-[var(--trk-text-muted)]">
          Showing {items.length} of {total} trip{total === 1 ? "" : "s"}.
        </p>
      ) : null}
    </div>
  );
}
