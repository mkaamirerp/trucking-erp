import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { OPS } from "../../routes";
import { useDispatchHomeDashboard } from "../../hooks/useDispatchHomeDashboard";

function Panel({
  title,
  count,
  children,
  className = "",
}: {
  title: string;
  count?: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`flex min-h-0 flex-col rounded-md border border-slate-200 bg-white shadow-sm ${className}`}
    >
      <header className="flex shrink-0 items-center justify-between border-b border-slate-100 px-2.5 py-1.5">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">{title}</h2>
        {count != null ? (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
            {count}
          </span>
        ) : null}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{children}</div>
    </section>
  );
}

function RowButton({
  to,
  primary,
  secondary,
  badge,
}: {
  to: string;
  primary: string;
  secondary?: string;
  badge?: string;
}) {
  return (
    <Link
      to={to}
      className="block border-b border-slate-100 px-2.5 py-1.5 text-left transition-colors hover:bg-slate-50 last:border-b-0"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[12px] font-medium text-slate-900">{primary}</div>
          {secondary ? (
            <div className="truncate text-[10px] text-slate-500">{secondary}</div>
          ) : null}
        </div>
        {badge ? (
          <span className="shrink-0 text-[10px] font-medium text-slate-500">{badge}</span>
        ) : null}
      </div>
    </Link>
  );
}

export default function DispatchHomeDashboard() {
  const {
    loading,
    error,
    partialErrors,
    drivers,
    inbound,
    assignQueue,
    podPanel,
    refetch,
  } = useDispatchHomeDashboard();

  const availableCount = drivers.filter((d) => d.status === "available").length;
  const unverifiedCount = drivers.filter((d) => d.status === "unverified").length;

  function driverBadge(status: (typeof drivers)[0]["status"]): { label: string; className: string } {
    switch (status) {
      case "available":
        return { label: "Avail", className: "bg-emerald-50 text-emerald-700" };
      case "executing":
        return { label: "In prog", className: "bg-violet-50 text-violet-800" };
      case "scheduled":
        return { label: "Scheduled", className: "bg-sky-50 text-sky-700" };
      case "unverified":
        return { label: "Unverified", className: "bg-slate-100 text-slate-600" };
      case "license_blocked":
        return { label: "Lic block", className: "bg-amber-50 text-amber-800" };
      default:
        return { label: status, className: "bg-slate-100 text-slate-600" };
    }
  }

  return (
    <div
      className="dispatch-home-dashboard flex h-[calc(100dvh-3.25rem)] min-h-[480px] flex-col bg-slate-100 text-slate-900"
      data-testid="dispatch-home-dashboard"
    >
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-3 py-1.5">
        <div>
          <h1 className="text-sm font-semibold text-slate-900">Home</h1>
          <p className="text-[10px] text-slate-500">Dispatch overview — live tenant data</p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={loading}
          className="rounded border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {(error || partialErrors.length > 0) && (
        <div className="shrink-0 border-b border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] text-amber-900">
          {error ? <div>{error}</div> : null}
          {partialErrors.length ? (
            <div className="text-amber-800">Partial: {partialErrors.join(" · ")}</div>
          ) : null}
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-2 p-2 dispatch-home-grid">
        <aside className="flex min-h-0 flex-col gap-2 dispatch-home-left">
          <Panel title="Drivers" count={drivers.length} className="flex-[1.1] min-h-0">
            {loading && !drivers.length ? (
              <p className="px-2.5 py-2 text-[11px] text-slate-500">Loading drivers…</p>
            ) : drivers.length === 0 ? (
              <p className="px-2.5 py-2 text-[11px] text-slate-500">No active drivers.</p>
            ) : (
              <ul>
                {drivers.map((row) => (
                  <li key={row.driver.id} className="border-b border-slate-100 px-2.5 py-1.5 last:border-b-0">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-[12px] font-medium">
                          {row.driver.first_name} {row.driver.last_name}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {row.truckLabel ?? "—"}
                          {row.tripNumber ? ` · ${row.tripNumber}` : ""}
                        </div>
                      </div>
                      <span
                        className={`shrink-0 rounded px-1 py-0.5 text-[9px] font-semibold uppercase ${driverBadge(row.status).className}`}
                      >
                        {driverBadge(row.status).label}
                      </span>
                    </div>
                    {row.licenseWarning ? (
                      <div className="mt-0.5 text-[10px] text-amber-700">{row.licenseWarning}</div>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
            <div className="border-t border-slate-100 px-2.5 py-1 text-[10px] text-slate-500">
              {availableCount} verified available
              {unverifiedCount ? ` · ${unverifiedCount} unverified (trip list may be incomplete)` : ""}
            </div>
          </Panel>

          <Panel title="Inbound to yard" count={inbound.length} className="flex-1 min-h-0">
            {loading && !inbound.length ? (
              <p className="px-2.5 py-2 text-[11px] text-slate-500">Loading…</p>
            ) : inbound.length === 0 ? (
              <p className="px-2.5 py-2 text-[11px] text-slate-500">
                No inbound yard rows from open future plans. Yard drops with an inbound trip appear here.
              </p>
            ) : (
              <ul>
                {inbound.map((row) => (
                  <li key={row.key}>
                    <RowButton
                      to={row.tripId ? OPS.TRIP_DETAIL(row.tripId) : OPS.FUTURE_MOVEMENT_PLAN_DETAIL(row.fmpPlanId!)}
                      primary={`${row.tripNumber ?? "Trip"} → ${row.loadNumber ?? "Load"}`}
                      secondary={`ETA ${row.etaLabel}`}
                      badge="Inbound"
                    />
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </aside>

        <main className="flex min-h-0 flex-col gap-2 dispatch-home-center">
          <Panel title="Loads to assign" count={assignQueue.length} className="flex-[1.2] min-h-0">
            {loading && !assignQueue.length ? (
              <p className="px-2.5 py-2 text-[11px] text-slate-500">Loading queue…</p>
            ) : assignQueue.length === 0 ? (
              <p className="px-2.5 py-2 text-[11px] text-slate-500">
                No open future plans or planned trips need attention.
              </p>
            ) : (
              <ul>
                {assignQueue.map((row) => (
                  <li key={`${row.kind}-${row.id}`}>
                    <RowButton
                      to={row.href}
                      primary={row.label}
                      secondary={`${row.sublabel} · ${row.loadCount} load(s)`}
                      badge={
                        row.kind === "fmp"
                          ? "FMP"
                          : row.queueKind === "needs_driver"
                            ? "Driver"
                            : "Equip"
                      }
                    />
                  </li>
                ))}
              </ul>
            )}
            <div className="border-t border-slate-100 px-2.5 py-1 text-[10px] text-slate-500">
              Assign via{" "}
              <Link to={OPS.TRIP_CONTAINER} className="text-sky-700 hover:underline">
                Trip Container
              </Link>{" "}
              or{" "}
              <Link to={OPS.FUTURE_MOVEMENT_PLANS} className="text-sky-700 hover:underline">
                Future plans
              </Link>
              .
            </div>
          </Panel>

          <Panel title="Delivered · POD not received" className="flex-1 min-h-0">
            <div className="px-2.5 py-3 text-[11px] leading-relaxed text-slate-600">
              <p className="font-medium text-slate-800">
                {podPanel.connected ? "Connected" : "Not connected"}
              </p>
              <p className="mt-2 text-slate-500">{podPanel.message}</p>
              <p className="mt-2 text-slate-500">
                Open a load workspace to upload or review POD evidence for a specific delivery.
              </p>
            </div>
          </Panel>
        </main>

        <aside className="flex min-h-0 flex-col dispatch-home-right">
          <Panel title="Driver messages" className="h-full min-h-0">
            <div className="flex h-full min-h-[200px] flex-col">
              <div className="flex-1 px-2.5 py-3 text-[11px] text-slate-600">
                <p className="font-medium text-slate-800">Not connected</p>
                <p className="mt-2 leading-relaxed text-slate-500">
                  Driver messaging (e.g. WhatsApp) is not integrated in TruckERP yet. This panel is reserved for a
                  future tenant-scoped messaging feed.
                </p>
              </div>
              <div className="shrink-0 border-t border-slate-100 bg-slate-50 px-2.5 py-2">
                <textarea
                  disabled
                  placeholder="Messaging unavailable"
                  className="w-full resize-none rounded border border-slate-200 bg-white px-2 py-1.5 text-[11px] text-slate-400"
                  rows={2}
                />
                <p className="mt-1 text-[10px] text-slate-400">Send is disabled until a messaging provider is configured.</p>
              </div>
            </div>
          </Panel>
        </aside>
      </div>

      <style>{`
        .dispatch-home-grid {
          grid-template-columns: minmax(200px, 230px) minmax(0, 1fr) minmax(220px, 260px);
        }
        @media (min-width: 1536px) {
          .dispatch-home-grid {
            grid-template-columns: minmax(220px, 240px) minmax(0, 1fr) minmax(250px, 270px);
          }
        }
        @media (max-width: 1100px) {
          .dispatch-home-grid {
            grid-template-columns: 1fr;
            grid-template-rows: auto;
          }
          .dispatch-home-dashboard {
            height: auto;
            min-height: calc(100dvh - 3.25rem);
          }
          .dispatch-home-left,
          .dispatch-home-center,
          .dispatch-home-right {
            max-height: 320px;
          }
        }
      `}</style>
    </div>
  );
}
