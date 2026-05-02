/**
 * Read-only trip operational shell (Phase 3A). Execution/custody UI comes later.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getTrip, type TripDetail } from "@/api";
import { OPS } from "@/routes";

function formatMoney(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

export default function TripWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const tripId = Number(id);
  const navigate = useNavigate();
  const [trip, setTrip] = useState<TripDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!Number.isFinite(tripId)) {
      setError("Invalid trip id");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const t = await getTrip(tripId);
      setTrip(t);
    } catch (e: unknown) {
      setTrip(null);
      setError(e instanceof Error ? e.message : "Failed to load trip");
    } finally {
      setLoading(false);
    }
  }, [tripId]);

  useEffect(() => {
    void load();
  }, [load]);

  const toolBtn =
    "rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-text-muted)] shadow-sm hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)]";

  return (
    <div className="flex min-h-screen flex-col bg-[var(--trk-bg)] text-[var(--trk-text)]">
      <header className="z-10 shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface)]">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
            <button type="button" onClick={() => navigate(OPS.TRIPS)} className={toolBtn}>
              ← Trips
            </button>
            <button type="button" onClick={() => navigate(OPS.DISPATCH)} className={toolBtn}>
              Dispatch
            </button>
            <div className="min-w-0">
              <div className="font-mono text-[11px] text-[var(--trk-text-muted)]">Trip container (read-only)</div>
              <h1 className="truncate text-lg font-semibold tracking-tight text-[var(--trk-text)]">
                {loading ? "Loading…" : trip ? `Trip #${trip.trip_number}` : "Trip"}
              </h1>
              {trip ? (
                <p className="mt-0.5 text-[12px] text-[var(--trk-text-muted)]">
                  {trip.status} · {trip.job_type}
                  {trip.cancelled_at ? (
                    <>
                      {" "}
                      · <span className="font-medium text-red-700/90">Cancelled {new Date(trip.cancelled_at).toLocaleString()}</span>
                    </>
                  ) : null}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6">
        {loading ? (
          <p className="text-sm text-[var(--trk-text-muted)]">Loading trip…</p>
        ) : error ? (
          <p className="text-sm text-red-700">{error}</p>
        ) : trip ? (
          <div className="space-y-8">
            <section className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] p-5">
              <h2 className="text-sm font-semibold text-[var(--trk-text)]">Equipment</h2>
              <p className="mt-3 text-sm text-[var(--trk-text-muted)]">
                <span className="font-medium text-[var(--trk-text)]">Driver: </span>
                {trip.driver
                  ? `${trip.driver.first_name} ${trip.driver.last_name}`
                  : trip.driver_id != null
                    ? `#${trip.driver_id}`
                    : "—"}
              </p>
              <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
                <span className="font-medium text-[var(--trk-text)]">Truck: </span>
                {trip.truck ? trip.truck.unit_number : trip.truck_id != null ? `#${trip.truck_id}` : "—"}
              </p>
              <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
                <span className="font-medium text-[var(--trk-text)]">Trailer: </span>
                {trip.trailer
                  ? `${trip.trailer.unit_number}${trip.trailer.trailer_type ? ` · ${trip.trailer.trailer_type}` : ""}`
                  : trip.trailer_id != null
                    ? `#${trip.trailer_id}`
                    : "—"}
              </p>
              {trip.assigned_at ? (
                <p className="mt-2 text-xs text-[var(--trk-text-muted)]">
                  Assigned {new Date(trip.assigned_at).toLocaleString()}
                </p>
              ) : null}
              {trip.cancelled_at ? (
                <p className="mt-2 text-xs font-medium text-red-700/90">
                  Cancelled {new Date(trip.cancelled_at).toLocaleString()}
                </p>
              ) : null}
            </section>

            <section className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] p-5">
              <h2 className="text-sm font-semibold text-[var(--trk-text)]">Member loads</h2>
              <p className="mt-2 text-sm text-[var(--trk-text-muted)]">
                Trip is the operational container. Loads below remain commercial records. Open a load for rate, broker, and
                document work.
              </p>
              {trip.member_loads.length === 0 ? (
                <p className="mt-4 text-sm italic text-[var(--trk-text-muted)]">No loads on this trip yet.</p>
              ) : (
                <ul className="mt-4 divide-y divide-[var(--trk-border)] rounded-lg border border-[var(--trk-border)]">
                  {trip.member_loads.map((m) => (
                    <li key={m.trip_load_id} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <Link
                          to={OPS.LOAD_DETAIL(m.load_id)}
                          className="font-medium text-[var(--trk-heading)] hover:underline"
                        >
                          {m.load_number}
                        </Link>
                        <div className="mt-1 text-xs text-[var(--trk-text-muted)]">
                          {m.broker_name_snapshot || "—"}
                          {m.broker_load_reference ? ` · Ref ${m.broker_load_reference}` : ""}
                          {m.commodity ? ` · ${m.commodity}` : ""}
                        </div>
                        {m.stop_route_summary ? (
                          <div className="mt-1 text-xs text-[var(--trk-text-muted)]">{m.stop_route_summary}</div>
                        ) : null}
                      </div>
                      <div className="shrink-0 text-right text-xs text-[var(--trk-text-muted)]">
                        <div>{m.status_within_trip}</div>
                        <div className="mt-1">
                          {formatMoney(m.rate)} / {formatMoney(m.customer_rate)}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-xl border border-dashed border-[var(--trk-border)] bg-[var(--trk-bg)] p-5">
              <h2 className="text-sm font-semibold text-[var(--trk-text)]">Execution (coming later)</h2>
              <p className="mt-2 text-sm text-[var(--trk-text-muted)]">
                Execution timeline, stops, and custody will be added in a later phase.
              </p>
            </section>

            {trip.legacy_dispatch_trip_id != null ? (
              <p className="text-[10px] text-[var(--trk-text-muted)]">
                Legacy dispatch id (debug): {trip.legacy_dispatch_trip_id}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
