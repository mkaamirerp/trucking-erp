/**
 * Trip Container = Dispatch Control Center — dispatcher-brain layout (focused trip + load stack).
 * Trip APIs only; no dispatch board; no drawer.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clsx } from "clsx";
import {
  addLoadToTrip,
  cancelTrip,
  createPlannedTrip,
  getLoad,
  getTrip,
  listDrivers,
  listLoads,
  listTrailers,
  listTrips,
  listTrucks,
  postTripExecutionSignal,
  removeLoadFromTrip,
  updateTripAssignment,
  type Driver,
  type Load,
  type LoadStop,
  type Trailer,
  type TripDetail,
  type TripListItem,
  type TripMemberLoad,
  type Truck,
  isOpenTripMembership,
} from "@/api";
import { OPS } from "@/routes";
import { formatRouteFromStops, sortedStops, formatStopCityState } from "@/utils/loadStops";
import { FuturePlaceholderPanels } from "./FuturePlaceholderPanels";

type LifecycleTab = "active" | "planned" | "assigned" | "in_progress" | "completed" | "problem_hold";

type ViewMode = "dispatch" | "driver";

const TAB_ORDER: { key: LifecycleTab; label: string }[] = [
  { key: "active", label: "Active" },
  { key: "planned", label: "Planned" },
  { key: "assigned", label: "Assigned" },
  { key: "in_progress", label: "In Progress" },
  { key: "completed", label: "Completed" },
  { key: "problem_hold", label: "Problem / Hold" },
];

/** Execution-boundary confirm: package flow is out of scope for this UI slice. */
const START_TRIP_CONFIRM_MESSAGE =
  "Start Trip begins execution (trip moves to in progress).\n\nDriver package tracking is future in this slice—not started or implied by this action.\n\nThis does not change Load.status, custody, or payroll.\n\nContinue?";

function formatMoney(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

function relativeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const sec = Math.floor((Date.now() - t) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function tripStatusBadgeClass(status: string): string {
  const s = (status || "").toLowerCase();
  if (s === "planned") return "bg-[var(--trk-border)] text-[var(--trk-text-muted)] border border-[var(--trk-border-strong)]";
  if (s === "assigned")
    return "border border-[var(--trk-accent)] bg-[var(--trk-surface-2)] text-[var(--trk-accent)]";
  if (s === "in_progress")
    return "border border-[var(--trk-success)] bg-[var(--trk-surface-2)] text-[var(--trk-success)]";
  if (s === "completed") return "bg-[var(--trk-surface)] text-[var(--trk-text-muted)] border border-[var(--trk-border)]";
  if (s === "cancelled")
    return "border border-[var(--trk-danger)] bg-[var(--trk-surface-2)] text-[var(--trk-danger)]";
  return "bg-[var(--trk-surface)] text-[var(--trk-text-muted)] border border-[var(--trk-border)]";
}

function driverFullName(d: Driver): string {
  return `${d.first_name ?? ""} ${d.last_name ?? ""}`.trim() || "—";
}

function driverInitials(d: Driver): string {
  const fn = (d.first_name ?? "").trim();
  const ln = (d.last_name ?? "").trim();
  const a = fn[0] ?? "";
  const b = ln[0] ?? "";
  const pair = `${a}${b}`.toUpperCase();
  if (pair) return pair;
  return "?";
}

/** Operational code until API exposes a dedicated driver_code field. */
function driverRosterCode(d: Driver): string {
  return `DRV-${d.id}`;
}

type DriverDispatchBadge =
  | "No Trip"
  | "Assigned"
  | "In Progress"
  | "Blocked"
  | "Inactive"
  | "Unknown";

type DriverCardContent = {
  badge: DriverDispatchBadge;
  badgeClass: string;
  line2: string;
  line3: string;
  line4Location: string;
  line4Signal: string;
};

function driverBadgeClass(badge: DriverDispatchBadge): string {
  switch (badge) {
    case "No Trip":
      return "border-[var(--trk-border-strong)] bg-[var(--trk-surface-2)] text-[var(--trk-text-muted)]";
    case "Assigned":
      return "border-[var(--trk-accent)] bg-[var(--trk-accent)]/12 text-[var(--trk-accent)]";
    case "In Progress":
      return "border-[var(--trk-success)] bg-[var(--trk-success)]/12 text-[var(--trk-success)]";
    case "Blocked":
    case "Inactive":
      return "border-[var(--trk-danger)] bg-[var(--trk-surface-2)] text-[var(--trk-danger)]";
    default:
      return "border-[var(--trk-border)] bg-[var(--trk-surface)] text-[var(--trk-text-muted)]";
  }
}

const DRIVER_CARD_LINE2 = "Driver type unknown · Terminal unknown";

function driverLicenseExpiryMs(d: Driver): number | null {
  const raw = d.license_expiry_date;
  if (!raw) return null;
  const t = new Date(raw).getTime();
  return Number.isNaN(t) ? null : t;
}

function driverLicenseExpired(d: Driver): boolean {
  const t = driverLicenseExpiryMs(d);
  if (t == null) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return t < today.getTime();
}

function driverLicenseExpiringSoon(d: Driver, withinDays = 30): boolean {
  const t = driverLicenseExpiryMs(d);
  if (t == null) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const limit = today.getTime() + withinDays * 86400000;
  return t >= today.getTime() && t <= limit;
}

/** Driver/person compliance only — never from load documents. */
function driverComplianceSignal(d: Driver): string {
  const t = driverLicenseExpiryMs(d);
  if (t == null) return "Compliance: Unknown";
  if (driverLicenseExpired(d)) return "License expired";
  if (driverLicenseExpiringSoon(d)) return "License expiring soon";
  return "License valid";
}

/** Line 3 — current operational snapshot from roster + active trip only. */
function driverCurrentLine(d: Driver, trip: TripListItem | null): string {
  if (!d.is_active) return "Inactive";
  if (driverLicenseExpired(d)) return "Not dispatchable";
  if (trip) return `On trip · ${trip.trip_number}`;
  return "No active trip";
}

function buildDriverCardContent(d: Driver, trip: TripListItem | null): DriverCardContent {
  const line4Location = "Unknown";
  const line4Signal = driverComplianceSignal(d);
  const line3 = driverCurrentLine(d, trip);

  if (!d.is_active) {
    return {
      badge: "Inactive",
      badgeClass: driverBadgeClass("Inactive"),
      line2: DRIVER_CARD_LINE2,
      line3,
      line4Location,
      line4Signal,
    };
  }

  if (driverLicenseExpired(d)) {
    return {
      badge: "Blocked",
      badgeClass: driverBadgeClass("Blocked"),
      line2: DRIVER_CARD_LINE2,
      line3,
      line4Location,
      line4Signal,
    };
  }

  if (!trip) {
    return {
      badge: "No Trip",
      badgeClass: driverBadgeClass("No Trip"),
      line2: DRIVER_CARD_LINE2,
      line3,
      line4Location,
      line4Signal,
    };
  }

  const st = (trip.status || "").toLowerCase();

  if (st === "in_progress") {
    return {
      badge: "In Progress",
      badgeClass: driverBadgeClass("In Progress"),
      line2: DRIVER_CARD_LINE2,
      line3,
      line4Location,
      line4Signal,
    };
  }

  if (st === "assigned" || st === "planned") {
    return {
      badge: "Assigned",
      badgeClass: driverBadgeClass("Assigned"),
      line2: DRIVER_CARD_LINE2,
      line3,
      line4Location,
      line4Signal,
    };
  }

  return {
    badge: "Unknown",
    badgeClass: driverBadgeClass("Unknown"),
    line2: DRIVER_CARD_LINE2,
    line3: "Status unknown",
    line4Location,
    line4Signal,
  };
}

function lifecycleFilterPillClass(key: LifecycleTab, selected: boolean): string {
  const base = "rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors";
  if (!selected) return clsx(base, "border-transparent text-[var(--trk-text-muted)] hover:border-[var(--trk-border)]");
  if (key === "active")
    return clsx(base, "border-[var(--trk-success)] bg-[var(--trk-success)]/12 text-[var(--trk-text)]");
  if (key === "assigned")
    return clsx(base, "border-[var(--trk-accent)] bg-[var(--trk-accent)]/12 text-[var(--trk-text)]");
  if (key === "in_progress")
    return clsx(base, "border-[var(--trk-success)] bg-[var(--trk-success)]/10 text-[var(--trk-text)]");
  if (key === "planned")
    return clsx(base, "border-[var(--trk-border-strong)] bg-[var(--trk-surface-2)] text-[var(--trk-text)]");
  if (key === "completed")
    return clsx(base, "border-[var(--trk-border)] bg-[var(--trk-surface)] text-[var(--trk-text-muted)]");
  return clsx(base, "border-[var(--trk-heading)] bg-[var(--trk-heading)] text-[var(--trk-btn-text)]");
}

function driverLine(t: TripListItem | TripDetail): string {
  if (t.driver) return `${t.driver.first_name} ${t.driver.last_name}`;
  if (t.driver_id != null) return `#${t.driver_id}`;
  return "Unassigned";
}

function truckLine(t: TripListItem | TripDetail): string {
  if (t.truck) return t.truck.unit_number;
  if (t.truck_id != null) return `#${t.truck_id}`;
  return "—";
}

function trailerLine(t: TripListItem | TripDetail): string {
  if (t.trailer) return `${t.trailer.unit_number}${t.trailer.trailer_type ? ` · ${t.trailer.trailer_type}` : ""}`;
  if (t.trailer_id != null) return `#${t.trailer_id}`;
  return "—";
}

function routeSummaryLine(t: TripListItem): string {
  const r = t.first_member?.stop_route_summary?.trim();
  if (r) return r;
  return "Route pending";
}

/** Route hint from trip detail first member snapshot. */
function routeSummaryFromDetail(d: TripDetail | null): string | null {
  const m = d?.member_loads?.find((x) => isOpenTripMembership(x));
  const r = m?.stop_route_summary?.trim();
  return r || null;
}

function nextActionSummary(t: Pick<TripListItem, "status" | "cancelled_at" | "driver_id">): string {
  const st = (t.status || "").toLowerCase();
  if (t.cancelled_at) return "Cancelled";
  if (st === "planned" && !t.driver_id) return "Needs assignment";
  if (st === "planned" && t.driver_id) return "Ready to send package";
  if (st === "assigned") return "Ready to start";
  if (st === "in_progress") return "In progress";
  if (st === "completed") return "Completed";
  return "—";
}

function isPlannedOpenForMembership(d: TripDetail): boolean {
  return (d.status || "").toLowerCase() === "planned" && d.cancelled_at == null;
}

function assignmentEditable(d: TripDetail): boolean {
  return d.cancelled_at == null && (d.status || "").toLowerCase() !== "in_progress";
}

function canStartExecution(d: TripDetail): boolean {
  return d.cancelled_at == null && (d.status || "").toLowerCase() === "assigned";
}

function canCancelTrip(d: TripDetail): boolean {
  return d.status === "planned" && d.cancelled_at == null;
}

function applySecondaryFilters(
  items: TripListItem[],
  opts: { driver: string; truck: string; trailer: string; todayOnly: boolean },
): TripListItem[] {
  let out = items;
  const dQ = opts.driver.trim().toLowerCase();
  const tQ = opts.truck.trim().toLowerCase();
  const rQ = opts.trailer.trim().toLowerCase();
  if (dQ) {
    out = out.filter((t) => {
      const name = t.driver ? `${t.driver.first_name} ${t.driver.last_name}`.toLowerCase() : "";
      return name.includes(dQ) || String(t.driver_id ?? "").includes(dQ);
    });
  }
  if (tQ) {
    out = out.filter((t) => (t.truck?.unit_number ?? "").toLowerCase().includes(tQ) || String(t.truck_id ?? "").includes(tQ));
  }
  if (rQ) {
    out = out.filter(
      (t) => (t.trailer?.unit_number ?? "").toLowerCase().includes(rQ) || String(t.trailer_id ?? "").includes(rQ),
    );
  }
  if (opts.todayOnly) {
    const day = new Date().toDateString();
    out = out.filter((t) => {
      const u = t.updated_at ? new Date(t.updated_at).toDateString() : "";
      return u === day;
    });
  }
  return out;
}

function docsIndicator(load: Load | null): { label: string; warn: boolean } {
  if (!load) return { label: "Docs ···", warn: false };
  if (load.review_required) return { label: "Review ⚠", warn: true };
  if (load.document_snapshot_confirmed_at) return { label: "Docs ✓", warn: false };
  return { label: "Docs ⚠", warn: true };
}

function LoadFutureOpsBar() {
  const chip =
    "rounded border border-dashed border-[var(--trk-border)] px-1.5 py-0.5 text-[9px] text-[var(--trk-text-muted)] opacity-80";
  return (
    <div className="mt-2 border-t border-[var(--trk-border)]/60 pt-2">
      <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
        Future operations · ·· soon
      </div>
      <div className="flex flex-wrap gap-1">
        <span className={chip}>Custody / Terminal</span>
        <span className={chip}>Handoff</span>
        <span className={chip}>Trailer transfer</span>
        <span className={chip}>Continuity across trips</span>
      </div>
    </div>
  );
}

function StopRow({
  loadId,
  stop,
  idx,
  open,
  stopKey,
  onToggle,
}: {
  loadId: number;
  stop: LoadStop;
  idx: number;
  open: boolean;
  stopKey: string;
  onToggle: () => void;
}) {
  const appt = [stop.appointment_date, stop.appointment_time_text].filter(Boolean).join(" · ");
  return (
    <li className="rounded border border-[var(--trk-border)]/80 bg-[var(--trk-surface)]">
      <div
        className="flex min-h-[30px] cursor-pointer flex-wrap items-center gap-2 px-2 py-0.5 text-[10px]"
        onClick={onToggle}
      >
        <span className="text-[var(--trk-text-muted)]">{open ? "▼" : "▶"}</span>
        <span className="tabular-nums text-[var(--trk-text-muted)]">{(stop.sequence ?? idx) + 1}</span>
        <span className="font-medium">{stop.stop_type}</span>
        <span>{stop.facility_name ?? "—"}</span>
        <span className="text-[var(--trk-text-muted)]">{formatStopCityState(stop)}</span>
        <span className="text-[var(--trk-text-muted)]">{appt || "—"}</span>
        <span className="text-[var(--trk-text-muted)]">{stop.reference_number ?? "—"}</span>
        <span className="ml-auto rounded border border-dashed border-[var(--trk-border)] px-1 text-[9px] text-[var(--trk-text-muted)]">
          Status ···
        </span>
      </div>
      {open ? (
        <div className="border-t border-[var(--trk-border)] px-3 py-1 text-[9px] text-[var(--trk-text-muted)]">
          {[stop.street, stop.city, stop.state_or_province, stop.postal_code, stop.country].filter(Boolean).join(", ") ||
            "—"}
          {stop.appointment_type ? ` · ${stop.appointment_type}` : ""}
          {stop.scheduled_at ? <div className="mt-0.5">Scheduled: {stop.scheduled_at}</div> : null}
          {stop.notes ? <div className="mt-1 italic">{stop.notes}</div> : null}
          {stop.commodity_notes ? <div className="mt-0.5">Commodity notes: {stop.commodity_notes}</div> : null}
          {stop.reference_number ? <div className="mt-0.5">Ref: {stop.reference_number}</div> : null}
          <div className="mt-1 rounded border border-dashed border-[var(--trk-border)] px-1 py-0.5 text-[9px]">
            Arrived · Loaded/Unloaded · Departed will appear here when stop execution is live.
          </div>
        </div>
      ) : null}
    </li>
  );
}

function ExpandedLoadSummary({
  load,
  onToggleStop,
  expandedStops,
}: {
  load: Load;
  onToggleStop: (loadId: number, stopKey: string) => void;
  expandedStops: Set<string>;
}) {
  const stops = sortedStops(load.stops);
  const docSnap = load.document_snapshot_confirmed_at
    ? `Snapshot confirmed ${new Date(load.document_snapshot_confirmed_at).toLocaleString()}`
    : "Document snapshot not confirmed";
  return (
    <div className="space-y-2 text-[10px]">
      {load.review_required ? (
        <div className="rounded border border-[var(--trk-warning)] bg-[var(--trk-surface-2)] px-2 py-1 text-[10px] text-[var(--trk-text)]">
          <span className="font-semibold text-[var(--trk-warning)]">Review: </span>
          Required before dispatch documents.
        </div>
      ) : null}
      {load.is_duplicate_of_load_id != null ? (
        <div className="rounded border border-[var(--trk-warning)] bg-[var(--trk-surface-2)] px-2 py-1 text-[10px] text-[var(--trk-text)]">
          <span className="font-semibold text-[var(--trk-warning)]">Duplicate: </span>
          Possible duplicate of load #{load.is_duplicate_of_load_id}
        </div>
      ) : null}
      <div className="grid gap-1 sm:grid-cols-2 text-[var(--trk-text-muted)]">
        <div>Broker: {load.broker_name_snapshot || load.broker?.name || "—"}</div>
        <div>Contact: {load.broker_contact_name_snapshot || load.broker_contact?.name || "—"}</div>
        <div>Ref: {load.broker_load_reference ?? "—"}</div>
        <div>Load #: {load.load_number ?? "—"}</div>
        <div>Commodity: {load.commodity ?? "—"}</div>
        <div>Equipment: {load.equipment_type ?? "—"}</div>
        <div>Weight: {load.estimated_weight != null ? `${load.estimated_weight} lb` : "—"}</div>
        <div>
          Rate: {formatMoney(load.rate)} / customer {formatMoney(load.customer_rate)}
        </div>
      </div>
      <div className="text-[9px] text-[var(--trk-text-muted)]">{docSnap}</div>
      {load.internal_notes?.trim() ? (
        <div className="text-[var(--trk-text-muted)]">
          <span className="font-semibold text-[var(--trk-text)]">Notes: </span>
          {load.internal_notes.trim().slice(0, 200)}
          {load.internal_notes.length > 200 ? "…" : ""}
        </div>
      ) : null}
      <div>
        <div className="mb-0.5 text-[9px] font-semibold uppercase text-[var(--trk-text-muted)]">Stops</div>
        <ul className="space-y-0.5">
          {stops.map((s, idx) => {
            const sk = `${s.id ?? idx}-${idx}`;
            const open = expandedStops.has(`${load.id}:${sk}`);
            return (
              <StopRow
                key={sk}
                loadId={load.id}
                stop={s}
                idx={idx}
                open={open}
                stopKey={sk}
                onToggle={() => onToggleStop(load.id, sk)}
              />
            );
          })}
        </ul>
      </div>
      <LoadFutureOpsBar />
      <Link
        to={OPS.LOAD_DETAIL(load.id)}
        className="inline-block rounded border border-[var(--trk-heading)]/40 px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-heading)]"
      >
        Open full Load Workspace
      </Link>
    </div>
  );
}

function SlimAssignmentPanel({
  tripId,
  detail,
  assignOk,
  onRefreshTripDetail,
  onRefreshList,
  btnPrimary,
}: {
  tripId: number;
  detail: TripDetail;
  assignOk: boolean;
  onRefreshTripDetail: (id: number) => void;
  onRefreshList: () => void;
  btnPrimary: string;
}) {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [trucks, setTrucks] = useState<Truck[]>([]);
  const [trailers, setTrailers] = useState<Trailer[]>([]);
  const [pickBusy, setPickBusy] = useState(false);
  const [draftD, setDraftD] = useState(String(detail.driver_id ?? ""));
  const [draftT, setDraftT] = useState(String(detail.truck_id ?? ""));
  const [draftR, setDraftR] = useState(String(detail.trailer_id ?? ""));
  const [saveBusy, setSaveBusy] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);

  useEffect(() => {
    setDraftD(String(detail.driver_id ?? ""));
    setDraftT(String(detail.truck_id ?? ""));
    setDraftR(String(detail.trailer_id ?? ""));
  }, [detail.driver_id, detail.truck_id, detail.trailer_id, detail.id]);

  useEffect(() => {
    if (!assignOk) return;
    let c = false;
    void (async () => {
      setPickBusy(true);
      try {
        const [dRes, tRes, rRes] = await Promise.all([
          listDrivers({ limit: 200 }),
          listTrucks({ page: 1, size: 200 }),
          listTrailers({ page: 1, size: 200 }),
        ]);
        if (!c) {
          setDrivers(dRes);
          setTrucks(tRes.items);
          setTrailers(rRes.items);
        }
      } finally {
        if (!c) setPickBusy(false);
      }
    })();
    return () => {
      c = true;
    };
  }, [assignOk, tripId]);

  if (!assignOk) {
    return <p className="text-[9px] text-[var(--trk-text-muted)]">Assignment locked for this trip status.</p>;
  }

  const saveAssignment = async () => {
    setSaveBusy(true);
    setActionErr(null);
    try {
      const driver_id = draftD.trim() === "" ? null : Number(draftD);
      const truck_id = draftT.trim() === "" ? null : Number(draftT);
      const trailer_id = draftR.trim() === "" ? null : Number(draftR);
      await updateTripAssignment(tripId, { driver_id, truck_id, trailer_id });
      onRefreshTripDetail(tripId);
      onRefreshList();
    } catch (e: unknown) {
      setActionErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaveBusy(false);
    }
  };

  return (
    <div className="space-y-2 border-t border-[var(--trk-border)]/60 pt-2">
      {pickBusy ? <p className="text-[9px] text-[var(--trk-text-muted)]">Loading pickers…</p> : null}
      <div className="grid gap-1 sm:grid-cols-3">
        <select
          value={draftD}
          onChange={(e) => setDraftD(e.target.value)}
          className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1 py-0.5 text-[10px]"
        >
          <option value="">— Driver —</option>
          {drivers.map((d) => (
            <option key={d.id} value={String(d.id)}>
              {d.first_name} {d.last_name}
            </option>
          ))}
        </select>
        <select
          value={draftT}
          onChange={(e) => setDraftT(e.target.value)}
          className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1 py-0.5 text-[10px]"
        >
          <option value="">— Truck —</option>
          {trucks.map((t) => (
            <option key={t.id} value={String(t.id)}>
              {t.unit_number}
            </option>
          ))}
        </select>
        <select
          value={draftR}
          onChange={(e) => setDraftR(e.target.value)}
          className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1 py-0.5 text-[10px]"
        >
          <option value="">— Trailer —</option>
          {trailers.map((r) => (
            <option key={r.id} value={String(r.id)}>
              {r.unit_number}
            </option>
          ))}
        </select>
      </div>
      <button type="button" className={btnPrimary} disabled={saveBusy} onClick={() => void saveAssignment()}>
        {saveBusy ? "…" : "Update assignment"}
      </button>
      {actionErr ? <p className="text-[9px] text-[var(--trk-danger)]">{actionErr}</p> : null}
    </div>
  );
}

function AddLoadPanel({
  tripId,
  memOpen,
  onRefreshTripDetail,
  onRefreshList,
  btn,
  btnPrimary,
}: {
  tripId: number;
  memOpen: boolean;
  onRefreshTripDetail: (id: number) => void;
  onRefreshList: () => void;
  btn: string;
  btnPrimary: string;
}) {
  const [addId, setAddId] = useState("");
  const [addBusy, setAddBusy] = useState(false);
  const [searchQ, setSearchQ] = useState("");
  const [searchRes, setSearchRes] = useState<Load[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);

  const runSearch = async () => {
    const q = searchQ.trim();
    if (!q) return;
    setSearchBusy(true);
    try {
      const p = await listLoads({ search: q, page: 1, size: 15 });
      setSearchRes(p.items);
    } finally {
      setSearchBusy(false);
    }
  };

  if (!memOpen) {
    return <p className="text-[9px] text-[var(--trk-text-muted)]">Add load is only available while trip is planned (not cancelled).</p>;
  }

  return (
    <div className="space-y-2 border-t border-[var(--trk-border)]/60 pt-2">
      <div className="flex flex-wrap gap-1">
        <input
          value={searchQ}
          onChange={(e) => setSearchQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void runSearch()}
          placeholder="Search loads…"
          className="min-w-[140px] flex-1 rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1 py-0.5 text-[10px]"
        />
        <button type="button" className={btn} disabled={searchBusy} onClick={() => void runSearch()}>
          Search
        </button>
      </div>
      {searchRes.length > 0 ? (
        <ul className="max-h-32 overflow-y-auto text-[10px]">
          {searchRes.map((row) => (
            <li key={row.id} className="flex justify-between gap-1 border-b border-[var(--trk-border)]/50 py-0.5">
              <span>
                #{row.load_number} · {row.broker_name_snapshot ?? "—"}
              </span>
              <button
                type="button"
                className={btnPrimary}
                disabled={addBusy}
                onClick={async () => {
                  setAddBusy(true);
                  try {
                    await addLoadToTrip(tripId, { load_id: row.id });
                    setSearchRes([]);
                    setSearchQ("");
                    onRefreshTripDetail(tripId);
                    onRefreshList();
                  } catch (e: unknown) {
                    alert(e instanceof Error ? e.message : "Add failed");
                  } finally {
                    setAddBusy(false);
                  }
                }}
              >
                Add
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-center gap-1">
        <input
          value={addId}
          onChange={(e) => setAddId(e.target.value)}
          placeholder="Load ID"
          className="w-24 rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1 py-0.5 text-[10px]"
        />
        <button
          type="button"
          className={btnPrimary}
          disabled={addBusy}
          onClick={async () => {
            const id = Number(addId.trim());
            if (!Number.isFinite(id) || id < 1) return;
            setAddBusy(true);
            try {
              await addLoadToTrip(tripId, { load_id: id });
              setAddId("");
              onRefreshTripDetail(tripId);
              onRefreshList();
            } catch (e: unknown) {
              alert(e instanceof Error ? e.message : "Add failed");
            } finally {
              setAddBusy(false);
            }
          }}
        >
          + Add by ID
        </button>
      </div>
    </div>
  );
}

function DriverRoutePlaceholder() {
  return (
    <div className="rounded border border-dashed border-[var(--trk-border)] bg-[var(--trk-bg)]/30 px-3 py-4 text-center text-[11px] text-[var(--trk-text-muted)]">
      Driver Route View will merge stops across loads when a trip-level itinerary API is available.
      <br />
      <span className="text-[10px]">Expand load blocks and open Dispatch View to work loads today.</span>
    </div>
  );
}

function buildMergedStopRows(
  members: TripMemberLoad[],
  loadById: Map<number, Load>,
): { loadNum: string; loadId: number; stop: LoadStop; key: string }[] {
  const rows: { loadNum: string; loadId: number; stop: LoadStop; key: string }[] = [];
  for (const m of members) {
    const load = loadById.get(m.load_id);
    if (!load?.stops?.length) continue;
    let i = 0;
    for (const s of sortedStops(load.stops)) {
      rows.push({
        loadNum: m.load_number ?? load.load_number ?? String(m.load_id),
        loadId: m.load_id,
        stop: s,
        key: `${m.load_id}-${String(s.id ?? i)}-${i}`,
      });
      i++;
    }
  }
  return rows;
}

function stopKindBadgeClass(stopType: string | undefined): string {
  const u = (stopType || "").toUpperCase();
  if (u === "PICKUP") return "border-[var(--trk-success)] bg-[var(--trk-success)]/15 text-[var(--trk-success)]";
  if (u === "DELIVERY" || u === "DROP") return "border-[var(--trk-accent)] bg-[var(--trk-accent)]/12 text-[var(--trk-accent)]";
  return "border-[var(--trk-border-strong)] bg-[var(--trk-surface-2)] text-[var(--trk-text-muted)]";
}

function TripMergedStopsTimeline({
  members,
  loadById,
  title = "Trip route",
}: {
  members: TripMemberLoad[];
  loadById: Map<number, Load>;
  title?: string;
}) {
  const rows = buildMergedStopRows(members, loadById);
  const missing = members.some((m) => {
    const lo = loadById.get(m.load_id);
    return !lo?.stops?.length;
  });
  const cap = 28;
  const slice = rows.slice(0, cap);

  if (rows.length === 0) {
    return (
      <div className="mb-3 rounded-lg border border-dashed border-[var(--trk-border)] bg-[var(--trk-surface)]/80 px-3 py-2.5">
        {missing ? (
          <p className="text-[10px] leading-snug text-[var(--trk-warning)]">
            Partial route — expand member loads below to fetch stops for a merged timeline.
          </p>
        ) : (
          <p className="text-[10px] text-[var(--trk-text-muted)]">No stops on active loads yet.</p>
        )}
      </div>
    );
  }

  return (
    <div className="mb-3 rounded-lg border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] px-2.5 py-2 shadow-sm">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--trk-border)] pb-1.5">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">{title}</span>
        <span className="font-mono text-[10px] font-semibold text-[var(--trk-text)]">{rows.length} stops</span>
      </div>
      {missing ? (
        <p className="mb-2 text-[9px] text-[var(--trk-warning)]">Showing loaded loads only — expand others for full sequence.</p>
      ) : null}
      <ol className="space-y-0">
        {slice.map((r, idx) => {
          const appt = [r.stop.appointment_date, r.stop.appointment_time_text].filter(Boolean).join(" · ");
          const isLast = idx === slice.length - 1;
          const u = (r.stop.stop_type || "").toUpperCase();
          const docsPending = u === "DELIVERY" || u === "DROP";
          const loadForStop = loadById.get(r.loadId) ?? null;
          return (
            <li key={r.key} className="flex gap-2">
              <div className="flex w-4 shrink-0 flex-col items-center pt-0.5">
                <span
                  className={clsx(
                    "h-2.5 w-2.5 shrink-0 rounded-full border-2",
                    u === "PICKUP"
                      ? "border-[var(--trk-success)] bg-[var(--trk-success)]/30"
                      : u === "DELIVERY" || u === "DROP"
                        ? "border-[var(--trk-accent)] bg-[var(--trk-accent)]/25"
                        : "border-[var(--trk-border-strong)] bg-[var(--trk-surface)]",
                  )}
                  aria-hidden
                />
                {!isLast ? <span className="my-0.5 w-px flex-1 min-h-[12px] bg-[var(--trk-border-strong)]" aria-hidden /> : null}
              </div>
              <div className={clsx("min-w-0 flex-1 pb-3", isLast && "pb-0")}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={clsx(
                      "rounded border px-1 py-0 text-[8px] font-bold uppercase tracking-wide",
                      stopKindBadgeClass(r.stop.stop_type),
                    )}
                  >
                    {r.stop.stop_type || "STOP"}
                  </span>
                  <span className="text-[10px] font-semibold text-[var(--trk-text)]">{r.stop.facility_name ?? "—"}</span>
                  <span className="text-[9px] text-[var(--trk-text-muted)]">{formatStopCityState(r.stop)}</span>
                </div>
                <div className="mt-0.5 text-[9px] text-[var(--trk-text-muted)]">
                  <span className="font-mono text-[var(--trk-text)]">LD-{r.loadNum}</span>
                  {appt ? <span> · {appt}</span> : null}
                  {r.stop.reference_number ? (
                    <span>
                      {" "}
                      · ref <span className="font-mono">{r.stop.reference_number}</span>
                    </span>
                  ) : null}
                </div>
                {docsPending && loadForStop && docsIndicator(loadForStop).warn ? (
                  <div className="mt-1 inline-flex items-center gap-1 rounded border border-[var(--trk-warning)]/60 bg-[var(--trk-warning)]/10 px-1.5 py-0.5 text-[8px] font-medium text-[var(--trk-warning)]">
                    <span aria-hidden>◆</span> Docs pending
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
      {rows.length > cap ? (
        <p className="mt-1 border-t border-[var(--trk-border)] pt-1.5 text-[9px] text-[var(--trk-text-muted)]">
          Showing first {cap} of {rows.length} stops.
        </p>
      ) : null}
    </div>
  );
}

function DriverRouteMerged({
  members,
  loadById,
}: {
  members: TripMemberLoad[];
  loadById: Map<number, Load>;
}) {
  const rows = buildMergedStopRows(members, loadById);
  if (rows.length === 0) {
    return <DriverRoutePlaceholder />;
  }
  return <TripMergedStopsTimeline members={members} loadById={loadById} title="Merged driver route" />;
}

function CockpitStatsSubbar({
  tabCounts,
  loadsOnSelectedTrip,
  warningsOnSelected,
  unassignedTrips,
}: {
  tabCounts: { active: number; assigned: number; in_progress: number };
  loadsOnSelectedTrip: number | null;
  warningsOnSelected: number;
  unassignedTrips: number;
}) {
  const pill =
    "rounded-full border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-0.5 text-[10px] text-[var(--trk-text-muted)]";
  const warnPill =
    warningsOnSelected > 0
      ? "rounded-full border border-[var(--trk-warning)] bg-[var(--trk-surface-2)] px-2 py-0.5 text-[10px] text-[var(--trk-text)]"
      : pill;
  const unPill =
    unassignedTrips > 0
      ? "rounded-full border border-[var(--trk-warning)]/80 bg-[var(--trk-warning)]/10 px-2 py-0.5 text-[10px] text-[var(--trk-text)]"
      : pill;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[10px] text-[var(--trk-text-muted)]">
      <span className="hidden font-mono text-[9px] text-[var(--trk-text-muted)] sm:inline">Summary</span>
      <span className={pill}>
        <span className="text-[var(--trk-success)]">●</span> Active{" "}
        <span className="font-mono font-semibold text-[var(--trk-text)]">{tabCounts.active}</span>
      </span>
      <span className={pill}>
        <span className="text-[var(--trk-accent)]">●</span> Assigned{" "}
        <span className="font-mono font-semibold text-[var(--trk-text)]">{tabCounts.assigned}</span>
      </span>
      <span className={pill}>
        <span className="text-[var(--trk-success)]">●</span> In progress{" "}
        <span className="font-mono font-semibold text-[var(--trk-text)]">{tabCounts.in_progress}</span>
      </span>
      <span className={unPill}>
        Unassigned planned{" "}
        <span className="font-mono font-semibold text-[var(--trk-warning)]">{unassignedTrips}</span>
      </span>
      <span className={pill}>
        Loads on trip{" "}
        <span className="font-mono font-semibold text-[var(--trk-text)]">{loadsOnSelectedTrip == null ? "—" : loadsOnSelectedTrip}</span>
      </span>
      <span className={warnPill}>
        Warnings <span className="font-mono font-semibold text-[var(--trk-warning)]">{warningsOnSelected}</span>
        <span className="ml-1 text-[9px] opacity-80">(cached)</span>
      </span>
    </div>
  );
}

function findActiveTripForDriver(driverId: number, trips: TripListItem[]): TripListItem | null {
  const hits = trips.filter(
    (t) =>
      t.driver_id === driverId &&
      !t.cancelled_at &&
      ["planned", "assigned", "in_progress"].includes((t.status || "").toLowerCase()),
  );
  if (hits.length === 0) return null;
  return [...hits].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())[0] ?? null;
}

function DriverCockpitCard({
  driver,
  trip,
  onPick,
}: {
  driver: Driver;
  trip: TripListItem | null;
  onPick: () => void;
}) {
  const card = buildDriverCardContent(driver, trip);
  const filterTitle = `Filter trips by ${driverFullName(driver)}`;
  const line4Full = `Location: ${card.line4Location} · ${card.line4Signal}`;

  return (
    <button
      type="button"
      className="w-full min-h-[88px] min-w-0 overflow-hidden border-b border-[var(--trk-border)] px-2.5 py-2.5 text-left hover:bg-[var(--trk-surface-2)]"
      onClick={onPick}
      title={filterTitle}
    >
      <div className="grid min-h-[72px] grid-cols-[40px_minmax(0,1fr)] gap-x-2.5 gap-y-0.5">
        <span
          className="row-span-4 flex h-10 w-10 shrink-0 items-center justify-center self-start rounded-full border border-[var(--trk-border-strong)] bg-[var(--trk-surface-2)] text-[12px] font-bold leading-none text-[var(--trk-heading)]"
          aria-hidden
        >
          {driverInitials(driver)}
        </span>
        <div className="col-start-2 flex min-w-0 items-start gap-1.5">
          <p
            className="flex min-w-0 flex-1 items-baseline gap-1 overflow-hidden text-[11px] leading-[1.35]"
            title={`${driverFullName(driver)} · ${driverRosterCode(driver)}`}
          >
            <span className="min-w-0 truncate font-semibold text-[var(--trk-text)]">{driverFullName(driver)}</span>
            <span className="shrink-0 text-[var(--trk-text-muted)]">·</span>
            <span className="shrink-0 font-mono text-[10px] text-[var(--trk-text-muted)]">{driverRosterCode(driver)}</span>
          </p>
          <span
            className={clsx(
              "mt-px max-w-[7.25rem] shrink-0 truncate rounded border px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide",
              card.badgeClass,
            )}
            title={card.badge}
          >
            {card.badge}
          </span>
        </div>
        <p className="col-start-2 min-w-0 text-[10px] leading-[1.35] text-[var(--trk-text-muted)]" title={card.line2}>
          {card.line2}
        </p>
        <p className="col-start-2 min-w-0 text-[10px] leading-[1.35] text-[var(--trk-text-muted)]" title={`Current: ${card.line3}`}>
          <span>Current: </span>
          <span className="text-[var(--trk-text)]">{card.line3}</span>
        </p>
        <p className="col-start-2 min-w-0 text-[10px] leading-[1.35] text-[var(--trk-text-muted)]" title={line4Full}>
          <span>Location: </span>
          <span className="text-[var(--trk-text)]">{card.line4Location}</span>
          <span> · </span>
          <span className="text-[var(--trk-text)]">{card.line4Signal}</span>
        </p>
      </div>
    </button>
  );
}

function DriverCockpitPanel({
  drivers,
  loading,
  error,
  tripsForMatch,
  onPickDriverName,
  railMode,
  onRailMode,
}: {
  drivers: Driver[];
  loading: boolean;
  error: string | null;
  tripsForMatch: TripListItem[];
  onPickDriverName: (name: string) => void;
  railMode: "available" | "all";
  onRailMode: (m: "available" | "all") => void;
}) {
  const tabBtn = (active: boolean) =>
    clsx(
      "flex-1 rounded border px-2 py-1 text-center text-[9px] font-semibold uppercase tracking-wide",
      active
        ? "border-[var(--trk-accent)] bg-[var(--trk-accent)]/12 text-[var(--trk-accent)]"
        : "border-transparent text-[var(--trk-text-muted)] hover:border-[var(--trk-border)]",
    );

  const renderRow = (d: Driver) => {
    const name = driverFullName(d);
    const trip = findActiveTripForDriver(d.id, tripsForMatch);
    return (
      <DriverCockpitCard key={d.id} driver={d} trip={trip} onPick={() => onPickDriverName(name)} />
    );
  };

  const available = drivers.filter((d) => !findActiveTripForDriver(d.id, tripsForMatch));
  const busy = drivers.filter((d) => findActiveTripForDriver(d.id, tripsForMatch));

  return (
    <aside className="flex min-h-0 min-w-0 flex-col border-[var(--trk-border)] bg-[var(--trk-bg)] lg:border-r">
      <div className="flex shrink-0 flex-col gap-1 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Drivers</span>
          <span className="rounded border border-dashed border-[var(--trk-border)] px-1 text-[7px] text-[var(--trk-text-muted)]">
            Rail
          </span>
        </div>
        <div className="flex gap-1">
          <button type="button" className={tabBtn(railMode === "available")} onClick={() => onRailMode("available")}>
            Available
          </button>
          <button type="button" className={tabBtn(railMode === "all")} onClick={() => onRailMode("all")}>
            All
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? <p className="p-2 text-[10px] text-[var(--trk-text-muted)]">Loading drivers…</p> : null}
        {error ? <p className="p-2 text-[10px] text-[var(--trk-danger)]">{error}</p> : null}
        {!loading && !error && drivers.length === 0 ? (
          <p className="p-2 text-[10px] text-[var(--trk-text-muted)]">No drivers returned.</p>
        ) : null}
        {railMode === "available" ? (
          <>
            {available.length === 0 && !loading ? (
              <p className="p-2 text-[9px] text-[var(--trk-text-muted)]">No drivers match “available” for trips in this filter.</p>
            ) : null}
            {available.map(renderRow)}
          </>
        ) : (
          <>
            {busy.length > 0 ? (
              <>
                <div className="sticky top-0 z-[1] border-b border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2 py-1 text-[8px] font-bold uppercase tracking-wider text-[var(--trk-accent)]">
                  On trip
                </div>
                {busy.map(renderRow)}
              </>
            ) : null}
            {available.length > 0 ? (
              <>
                <div className="sticky top-0 z-[1] border-b border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2 py-1 text-[8px] font-bold uppercase tracking-wider text-[var(--trk-success)]">
                  Available
                </div>
                {available.map(renderRow)}
              </>
            ) : null}
          </>
        )}
      </div>
    </aside>
  );
}

function CommsCockpitPlaceholder({
  tab,
  onTab,
  tripLabel,
  driverHint,
}: {
  tab: "msgs" | "notes";
  onTab: (t: "msgs" | "notes") => void;
  tripLabel: string;
  driverHint?: string;
}) {
  const bubbleIn =
    "max-w-[92%] rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2 py-1.5 text-[9px] leading-snug text-[var(--trk-text)]";
  const bubbleOut =
    "max-w-[92%] rounded-lg border border-[var(--trk-accent)]/40 bg-[var(--trk-accent)]/12 px-2 py-1.5 text-[9px] leading-snug text-[var(--trk-text)]";

  return (
    <aside className="flex min-h-0 min-w-0 flex-col border-[var(--trk-border)] bg-[var(--trk-bg)] lg:border-l">
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Comms</span>
        <span className="rounded border border-dashed border-[var(--trk-border)] px-1 text-[8px] text-[var(--trk-text-muted)]">
          PREVIEW
        </span>
      </div>
      <div className="flex shrink-0 border-b border-[var(--trk-border)]">
        <button
          type="button"
          className={clsx(
            "flex-1 border-b-2 py-1.5 text-center text-[10px] font-medium",
            tab === "msgs"
              ? "border-[var(--trk-accent)] text-[var(--trk-accent)]"
              : "border-transparent text-[var(--trk-text-muted)]",
          )}
          onClick={() => onTab("msgs")}
        >
          Messages
        </button>
        <button
          type="button"
          className={clsx(
            "flex-1 border-b-2 py-1.5 text-center text-[10px] font-medium",
            tab === "notes"
              ? "border-[var(--trk-accent)] text-[var(--trk-accent)]"
              : "border-transparent text-[var(--trk-text-muted)]",
          )}
          onClick={() => onTab("notes")}
        >
          Notes
        </button>
      </div>
      <div className="shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2 py-1 text-[9px] text-[var(--trk-text-muted)]">
        Thread · <span className="font-mono text-[var(--trk-text)]">{tripLabel}</span>
        {driverHint ? (
          <>
            {" "}
            · <span className="text-[var(--trk-text)]">{driverHint}</span>
          </>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {tab === "msgs" ? (
          <div className="space-y-2">
            <p className="text-[8px] font-semibold uppercase tracking-wide text-[var(--trk-warning)]">
              Illustrative layout only — not live data or send.
            </p>
            <div className="flex justify-start">
              <div className={bubbleIn}>
                <div className="mb-0.5 text-[8px] font-semibold text-[var(--trk-text-muted)]">
                  {driverHint ?? "Driver"} · 08:12
                </div>
                On site for pickup at DC-2. ETA to first delivery unchanged for {tripLabel}.
              </div>
            </div>
            <div className="flex justify-end">
              <div className={bubbleOut}>
                <div className="mb-0.5 text-[8px] font-semibold text-[var(--trk-accent)]">You · 08:14</div>
                Copy — hold dispatch on stop 3 until docs clear. (Preview text)
              </div>
            </div>
            <div className="flex justify-start">
              <div className={bubbleIn}>
                <div className="mb-0.5 text-[8px] font-semibold text-[var(--trk-text-muted)]">
                  {driverHint ?? "Driver"} · 08:19
                </div>
                10-4. Waiting on revised PO #.
              </div>
            </div>
            <div className="mt-3 space-y-1.5 border-t border-[var(--trk-border)] pt-2">
              <div className="text-[8px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Other threads ··· soon</div>
              <div className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1 text-[9px] text-[var(--trk-text-muted)] opacity-70">
                TRP-XXXX · last message preview…
              </div>
              <div className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1 text-[9px] text-[var(--trk-text-muted)] opacity-70">
                TRP-YYYY · last message preview…
              </div>
            </div>
            <div className="mt-2 flex gap-1">
              <textarea
                readOnly
                disabled
                rows={2}
                className="min-h-0 flex-1 resize-none rounded border border-dashed border-[var(--trk-border)] bg-[var(--trk-surface)] p-1.5 text-[9px] text-[var(--trk-text-muted)]"
                placeholder="Message (disabled)"
              />
              <button
                type="button"
                className="shrink-0 self-end rounded border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2 py-1 text-[9px] font-semibold text-[var(--trk-text-muted)] opacity-50"
                disabled
                title="Send is not available in this slice"
              >
                Send
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-2 text-[10px] text-[var(--trk-text-muted)]">
            <p>
              Aggregated dispatch notes may appear here later. Use <strong className="text-[var(--trk-text)]">Load Workspace</strong>{" "}
              for editable notes today.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}

function LoadStackBlock({
  tripId,
  m,
  memOpen,
  expanded,
  onToggleExpand,
  load,
  loadLoading,
  loadErr,
  expandedStops,
  onToggleStop,
  onRefreshList,
  onDetailRefresh,
  btn,
  btnDanger,
}: {
  tripId: number;
  m: TripMemberLoad;
  memOpen: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  load: Load | null;
  loadLoading: boolean;
  loadErr: string | null;
  expandedStops: Set<string>;
  onToggleStop: (loadId: number, stopKey: string) => void;
  onRefreshList: () => void;
  onDetailRefresh: () => void;
  btn: string;
  btnDanger: string;
}) {
  const broker = m.broker_name_snapshot ?? load?.broker_name_snapshot ?? load?.broker?.name ?? "—";
  const ref = m.broker_load_reference ?? load?.broker_load_reference ?? "—";
  const rateLine = `${formatMoney(m.rate ?? load?.rate)}${m.customer_rate != null || load?.customer_rate != null ? ` · cust ${formatMoney(m.customer_rate ?? load?.customer_rate)}` : ""}`;
  const route = load ? formatRouteFromStops(load.stops) : m.stop_route_summary || "Route pending — expand to load stops";
  const docs = docsIndicator(load);
  const statusTrip = m.status_within_trip || "—";

  return (
    <article className="rounded-lg border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] shadow-sm">
      <div
        role="button"
        tabIndex={0}
        className="flex w-full cursor-pointer flex-col gap-1 px-3 py-2 text-left hover:bg-[var(--trk-border)]/15"
        onClick={onToggleExpand}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggleExpand();
          }
        }}
      >
        <div className="flex gap-2">
          <div className="min-w-0 flex-1">
            <span className="text-[11px] font-bold tracking-tight text-[var(--trk-text)]">
              LOAD {m.load_number} · {broker}
            </span>
            <div className="mt-1 text-[10px] text-[var(--trk-text-muted)]">
              REF {ref} · {rateLine}{" "}
              <span className={docs.warn ? "text-[var(--trk-warning)]" : ""}>{docs.label}</span>
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <div className="flex flex-wrap justify-end gap-0.5">
              <span
                className={clsx(
                  "rounded border px-1 py-0 text-[8px] font-bold uppercase",
                  docs.warn
                    ? "border-[var(--trk-warning)] text-[var(--trk-warning)]"
                    : "border-[var(--trk-success)] text-[var(--trk-success)]",
                )}
              >
                Docs
              </span>
              <span
                className={clsx(
                  "rounded border px-1 py-0 text-[8px] font-bold uppercase",
                  m.rate != null || load?.rate != null
                    ? "border-[var(--trk-success)] text-[var(--trk-success)]"
                    : "border-[var(--trk-border)] text-[var(--trk-text-muted)]",
                )}
              >
                Rate
              </span>
              <span className="rounded border border-dashed border-[var(--trk-border)] px-1 py-0 text-[8px] font-semibold uppercase text-[var(--trk-text-muted)]">
                Custody
              </span>
            </div>
            <span className="text-[10px] leading-none text-[var(--trk-text-muted)]">{expanded ? "▼" : "▶"}</span>
          </div>
        </div>
        <div className="text-[10px] text-[var(--trk-text)]">
          <span className="font-semibold text-[var(--trk-text-muted)]">Route: </span>
          {route}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[9px]">
          <span className="rounded bg-[var(--trk-border)]/40 px-1.5 py-0.5 font-medium text-[var(--trk-text)]">On trip: {statusTrip}</span>
          <span className="rounded border border-dashed border-[var(--trk-border)] px-1.5 py-0.5 text-[var(--trk-text-muted)]">
            Custody ···
          </span>
          <span className="rounded border border-dashed border-[var(--trk-border)] px-1.5 py-0.5 text-[var(--trk-text-muted)]">
            Lifecycle ···
          </span>
          <span className="rounded border border-dashed border-[var(--trk-border)] px-1.5 py-0.5 text-[var(--trk-text-muted)]">
            Next: terminal / handoff ··· soon
          </span>
        </div>
        <div className="flex flex-wrap gap-1 pt-1" onClick={(e) => e.stopPropagation()}>
          <Link to={OPS.LOAD_DETAIL(m.load_id)} className={btn} onClick={(e) => e.stopPropagation()}>
            Open in Load Workspace ↗
          </Link>
          {memOpen ? (
            <button
              type="button"
              className={btnDanger}
              onClick={async (e) => {
                e.stopPropagation();
                if (!window.confirm(`Remove load ${m.load_number} from trip?`)) return;
                try {
                  await removeLoadFromTrip(tripId, m.load_id);
                  onDetailRefresh();
                  onRefreshList();
                } catch (err: unknown) {
                  alert(err instanceof Error ? err.message : "Remove failed");
                }
              }}
            >
              Remove
            </button>
          ) : null}
          <span className={btn + " cursor-not-allowed opacity-50"} title="··· soon">
            Handoff ··· soon
          </span>
          <span className={btn + " cursor-not-allowed opacity-50"} title="··· soon">
            Transfer ··· soon
          </span>
        </div>
      </div>
      {expanded ? (
        <div className="border-t border-[var(--trk-border)] bg-[var(--trk-bg)]/25 px-3 py-2">
          {loadLoading ? <p className="text-[9px] text-[var(--trk-text-muted)]">Loading load…</p> : null}
          {loadErr ? <p className="text-[9px] text-[var(--trk-danger)]">{loadErr}</p> : null}
          {load ? <ExpandedLoadSummary load={load} onToggleStop={onToggleStop} expandedStops={expandedStops} /> : null}
        </div>
      ) : null}
    </article>
  );
}

export default function TripContainerPage() {
  const navigate = useNavigate();
  const [lifecycleTab, setLifecycleTab] = useState<LifecycleTab>("active");
  const [searchInput, setSearchInput] = useState("");
  const [searchDebounced, setSearchDebounced] = useState("");
  const [trips, setTrips] = useState<TripListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [tabCounts, setTabCounts] = useState<{ active: number; planned: number; assigned: number; in_progress: number; completed: number }>({
    active: 0,
    planned: 0,
    assigned: 0,
    in_progress: 0,
    completed: 0,
  });

  const [secDriver, setSecDriver] = useState("");
  const [secTruck, setSecTruck] = useState("");
  const [secTrailer, setSecTrailer] = useState("");
  const [secToday, setSecToday] = useState(false);

  const [focusedTripId, setFocusedTripId] = useState<number | null>(null);
  const [tripDetailById, setTripDetailById] = useState<Map<number, TripDetail>>(() => new Map());
  const [tripDetailLoading, setTripDetailLoading] = useState(false);
  const [tripDetailError, setTripDetailError] = useState<string | null>(null);

  const [expandedLoads, setExpandedLoads] = useState<Set<number>>(() => new Set());
  const [loadById, setLoadById] = useState<Map<number, Load>>(() => new Map());
  const [loadLoading, setLoadLoading] = useState<Set<number>>(() => new Set());
  const [loadError, setLoadError] = useState<Map<number, string>>(() => new Map());
  const [expandedStops, setExpandedStops] = useState<Set<string>>(() => new Set());

  const [viewMode, setViewMode] = useState<ViewMode>("dispatch");
  const [showAssignment, setShowAssignment] = useState(false);
  const [showAddLoad, setShowAddLoad] = useState(false);
  const [newTripBusy, setNewTripBusy] = useState(false);

  const [driversList, setDriversList] = useState<Driver[]>([]);
  const [driversLoading, setDriversLoading] = useState(false);
  const [driversError, setDriversError] = useState<string | null>(null);
  const [commsTab, setCommsTab] = useState<"msgs" | "notes">("msgs");
  const [driverRailMode, setDriverRailMode] = useState<"available" | "all">("available");
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [showStartConfirm, setShowStartConfirm] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setSearchDebounced(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    if (lifecycleTab === "problem_hold") return;
    let cancelled = false;
    setDriversLoading(true);
    setDriversError(null);
    void listDrivers({ limit: 200 })
      .then((d) => {
        if (!cancelled) setDriversList(d);
      })
      .catch((e) => {
        if (!cancelled) setDriversError(e instanceof Error ? e.message : "Failed to load drivers");
      })
      .finally(() => {
        if (!cancelled) setDriversLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [lifecycleTab]);

  const refreshTabCounts = useCallback(async () => {
    const q = searchDebounced.trim() || undefined;
    try {
      const [p, a, i, c] = await Promise.all([
        listTrips({ page: 1, size: 1, search: q, status: "planned" }),
        listTrips({ page: 1, size: 1, search: q, status: "assigned" }),
        listTrips({ page: 1, size: 1, search: q, status: "in_progress" }),
        listTrips({ page: 1, size: 1, search: q, status: "completed" }),
      ]);
      setTabCounts({
        planned: p.total ?? 0,
        assigned: a.total ?? 0,
        in_progress: i.total ?? 0,
        completed: c.total ?? 0,
        active: (p.total ?? 0) + (a.total ?? 0) + (i.total ?? 0),
      });
    } catch {
      /* best-effort */
    }
  }, [searchDebounced]);

  useEffect(() => {
    void refreshTabCounts();
  }, [refreshTabCounts]);

  const fetchTripList = useCallback(async () => {
    setLoading(true);
    setListError(null);
    const q = searchDebounced.trim() || undefined;
    try {
      if (lifecycleTab === "problem_hold") {
        setTrips([]);
        setLoading(false);
        return;
      }
      if (lifecycleTab === "active") {
        const [p, a, i] = await Promise.all([
          listTrips({ page: 1, size: 100, search: q, status: "planned" }),
          listTrips({ page: 1, size: 100, search: q, status: "assigned" }),
          listTrips({ page: 1, size: 100, search: q, status: "in_progress" }),
        ]);
        const map = new Map<number, TripListItem>();
        for (const res of [p, a, i]) {
          for (const t of res.items) {
            if (t.cancelled_at) continue;
            map.set(t.id, t);
          }
        }
        setTrips(
          [...map.values()].sort((x, y) => new Date(y.updated_at).getTime() - new Date(x.updated_at).getTime()),
        );
      } else {
        const res = await listTrips({ page: 1, size: 100, search: q, status: lifecycleTab });
        setTrips(res.items ?? []);
      }
    } catch (e: unknown) {
      setListError(e instanceof Error ? e.message : "Failed to load trips");
      setTrips([]);
    } finally {
      setLoading(false);
    }
  }, [lifecycleTab, searchDebounced]);

  useEffect(() => {
    void fetchTripList();
  }, [fetchTripList]);

  const filteredTrips = useMemo(
    () => applySecondaryFilters(trips, { driver: secDriver, truck: secTruck, trailer: secTrailer, todayOnly: secToday }),
    [trips, secDriver, secTruck, secTrailer, secToday],
  );

  useEffect(() => {
    if (filteredTrips.length === 0) {
      setFocusedTripId(null);
      return;
    }
    setFocusedTripId((prev) => {
      if (prev != null && filteredTrips.some((t) => t.id === prev)) return prev;
      return filteredTrips[0].id;
    });
  }, [filteredTrips]);

  useEffect(() => {
    setExpandedLoads(new Set());
    setExpandedStops(new Set());
    setShowAssignment(false);
    setShowAddLoad(false);
    setShowCancelConfirm(false);
    setShowStartConfirm(false);
  }, [focusedTripId]);

  const focusedListItem = useMemo(
    () => (focusedTripId != null ? filteredTrips.find((t) => t.id === focusedTripId) ?? null : null),
    [filteredTrips, focusedTripId],
  );

  const focusedDetail = focusedTripId != null ? tripDetailById.get(focusedTripId) ?? null : null;

  const refreshTripDetail = useCallback(async (id: number) => {
    try {
      const d = await getTrip(id);
      setTripDetailById((m) => new Map(m).set(id, d));
    } catch {
      /* keep prior */
    }
  }, []);

  useEffect(() => {
    if (focusedTripId == null) {
      setTripDetailError(null);
      setTripDetailLoading(false);
      return;
    }
    let cancelled = false;
    setTripDetailLoading(true);
    setTripDetailError(null);
    void (async () => {
      try {
        const d = await getTrip(focusedTripId);
        if (!cancelled) {
          setTripDetailById((m) => new Map(m).set(focusedTripId, d));
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setTripDetailError(e instanceof Error ? e.message : "Failed to load trip");
        }
      } finally {
        if (!cancelled) setTripDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [focusedTripId]);

  const toggleLoadExpand = useCallback(
    async (loadId: number) => {
      setExpandedLoads((prev) => {
        const n = new Set(prev);
        if (n.has(loadId)) n.delete(loadId);
        else n.add(loadId);
        return n;
      });
      if (loadById.has(loadId)) return;
      setLoadLoading((s) => new Set(s).add(loadId));
      setLoadError((m) => {
        const x = new Map(m);
        x.delete(loadId);
        return x;
      });
      try {
        const lo = await getLoad(loadId);
        setLoadById((m) => new Map(m).set(loadId, lo));
      } catch (e: unknown) {
        setLoadError((m) => new Map(m).set(loadId, e instanceof Error ? e.message : "Failed to load"));
      } finally {
        setLoadLoading((s) => {
          const n = new Set(s);
          n.delete(loadId);
          return n;
        });
      }
    },
    [loadById],
  );

  const onNewTrip = useCallback(async () => {
    setNewTripBusy(true);
    try {
      const t = await createPlannedTrip({});
      navigate(OPS.TRIP_DETAIL(t.id));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Could not create trip");
    } finally {
      setNewTripBusy(false);
    }
  }, [navigate]);

  const btn = "rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-text-muted)] hover:bg-[var(--trk-border)] disabled:opacity-45";
  const btnPrimary = "rounded border border-[var(--trk-heading)]/50 bg-[var(--trk-heading)]/15 px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-heading)] hover:bg-[var(--trk-heading)]/25 disabled:opacity-45";
  const btnDanger =
    "rounded border border-[var(--trk-danger)] bg-[var(--trk-surface-2)] px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-danger)] hover:opacity-90 disabled:opacity-45";
  const btnOutlineAccent =
    "rounded border border-[var(--trk-accent)]/55 bg-transparent px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-accent)] hover:bg-[var(--trk-accent)]/10 disabled:opacity-40";

  const orientation = focusedDetail ?? focusedListItem;
  const routeStrip =
    (focusedListItem && routeSummaryLine(focusedListItem)) ||
    routeSummaryFromDetail(focusedDetail) ||
    "Route pending";
  const nextAct =
    orientation && "status" in orientation
      ? nextActionSummary({
          status: orientation.status,
          cancelled_at: "cancelled_at" in orientation ? orientation.cancelled_at : null,
          driver_id: orientation.driver_id ?? null,
        })
      : "—";

  const activeMembers = useMemo(
    () => (focusedDetail?.member_loads ?? []).filter((m) => isOpenTripMembership(m)),
    [focusedDetail],
  );
  const warningsOnSelected = useMemo(() => {
    let n = 0;
    for (const m of activeMembers) {
      const lo = loadById.get(m.load_id);
      if (!lo) continue;
      if (lo.review_required) n++;
      if (lo.is_duplicate_of_load_id != null) n++;
    }
    return n;
  }, [activeMembers, loadById]);

  const unassignedTripCount = useMemo(
    () =>
      trips.filter(
        (t) =>
          !t.cancelled_at &&
          (t.status || "").toLowerCase() === "planned" &&
          (t.driver_id == null || t.driver_id === undefined),
      ).length,
    [trips],
  );

  const memOpen = focusedDetail ? isPlannedOpenForMembership(focusedDetail) : false;

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[var(--trk-bg)] text-[var(--trk-text)]">
      <header className="shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-sm font-semibold tracking-tight text-[var(--trk-text)]">Trip Container</h1>
            <p className="text-[10px] text-[var(--trk-text-muted)]">Dispatch Control Center</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Trip #, load ref, broker…"
              className="min-w-[180px] rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1 text-[11px] text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)]"
            />
            <button type="button" className={btnPrimary} disabled={newTripBusy} onClick={() => void onNewTrip()}>
              {newTripBusy ? "…" : "+ New trip"}
            </button>
          </div>
        </div>

        <div className="mt-2 flex flex-wrap gap-1">
          {TAB_ORDER.map(({ key, label }) => {
            if (key === "problem_hold") {
              return (
                <span
                  key={key}
                  className="cursor-not-allowed rounded-full border border-dashed border-[var(--trk-border)] px-2 py-0.5 text-[10px] text-[var(--trk-text-muted)] opacity-70"
                  title="Future only — not implemented"
                >
                  {label} · FUTURE
                </span>
              );
            }
            const count =
              key === "active"
                ? tabCounts.active
                : key === "planned"
                  ? tabCounts.planned
                  : key === "assigned"
                    ? tabCounts.assigned
                    : key === "in_progress"
                      ? tabCounts.in_progress
                      : tabCounts.completed;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setLifecycleTab(key)}
                className={lifecycleFilterPillClass(key, lifecycleTab === key)}
              >
                {label} · {count}
              </button>
            );
          })}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-[var(--trk-text-muted)]">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={secToday} onChange={(e) => setSecToday(e.target.checked)} />
            Today
          </label>
          <input
            value={secDriver}
            onChange={(e) => setSecDriver(e.target.value)}
            placeholder="Driver"
            className="w-24 rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1.5 py-0.5 text-[10px]"
          />
          <input
            value={secTruck}
            onChange={(e) => setSecTruck(e.target.value)}
            placeholder="Truck"
            className="w-20 rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1.5 py-0.5 text-[10px]"
          />
          <input
            value={secTrailer}
            onChange={(e) => setSecTrailer(e.target.value)}
            placeholder="Trailer"
            className="w-20 rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1.5 py-0.5 text-[10px]"
          />
          <button
            type="button"
            className={btn}
            onClick={() => {
              setSecDriver("");
              setSecTruck("");
              setSecTrailer("");
              setSecToday(false);
            }}
          >
            Clear All
          </button>
        </div>
      </header>

      {lifecycleTab !== "problem_hold" ? (
        <CockpitStatsSubbar
          tabCounts={{ active: tabCounts.active, assigned: tabCounts.assigned, in_progress: tabCounts.in_progress }}
          loadsOnSelectedTrip={focusedDetail ? activeMembers.length : null}
          warningsOnSelected={warningsOnSelected}
          unassignedTrips={unassignedTripCount}
        />
      ) : null}

      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="shrink-0 px-3 pt-2">
          {listError ? (
            <p className="mb-2 text-xs text-[var(--trk-danger)]">
              {listError}{" "}
              <button type="button" className={btn} onClick={() => void fetchTripList()}>
                Retry
              </button>
            </p>
          ) : null}
        </div>

        {lifecycleTab === "problem_hold" ? (
          <div className="overflow-auto px-3 py-3">
            <p className="text-[11px] text-[var(--trk-text-muted)]">
              Problem / Hold is a <strong>future</strong> filter only — not implemented.
            </p>
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)_auto] lg:grid-cols-[clamp(280px,min(320px,30vw),360px)_minmax(0,1fr)_clamp(260px,min(288px,26vw),340px)] lg:grid-rows-1">
            <DriverCockpitPanel
              drivers={driversList}
              loading={driversLoading}
              error={driversError}
              tripsForMatch={filteredTrips}
              onPickDriverName={(name) => setSecDriver(name)}
              railMode={driverRailMode}
              onRailMode={setDriverRailMode}
            />
            <div className="min-h-0 min-w-0 overflow-y-auto border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-2 lg:border-x">
              {loading ? (
          <div className="space-y-2 py-6">
            <div className="h-8 animate-pulse rounded bg-[var(--trk-border)]/40" />
            <div className="h-24 animate-pulse rounded bg-[var(--trk-border)]/30" />
            <div className="h-24 animate-pulse rounded bg-[var(--trk-border)]/30" />
          </div>
        ) : filteredTrips.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center text-[var(--trk-text-muted)]">
            <div className="mb-2 text-2xl" aria-hidden>
              🚛
            </div>
            <p className="text-sm">No trips match this filter.</p>
            <button
              type="button"
              className={clsx(btn, "mt-3")}
              onClick={() => {
                setSearchInput("");
                setSecDriver("");
                setSecTruck("");
                setSecTrailer("");
                setSecToday(false);
              }}
            >
              Clear filters
            </button>
          </div>
        ) : (
          <>
            <div className="mb-1 flex items-center justify-between gap-2 text-[9px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">
              <span>Select trip</span>
              <span className="font-mono text-[8px] font-normal normal-case text-[var(--trk-text-muted)]">
                {filteredTrips.length} in view
              </span>
            </div>
            <div className="mb-3 -mx-0.5 flex gap-1 overflow-x-auto pb-1">
              {filteredTrips.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setFocusedTripId(t.id)}
                  className={clsx(
                    "shrink-0 rounded-lg border px-2.5 py-1.5 text-left text-[10px] leading-tight shadow-sm transition-colors",
                    focusedTripId === t.id
                      ? "border-[var(--trk-accent)] bg-[var(--trk-accent)]/12 text-[var(--trk-text)] ring-1 ring-[var(--trk-accent)]/25"
                      : "border-[var(--trk-border)] bg-[var(--trk-surface)] text-[var(--trk-text-muted)] hover:border-[var(--trk-accent)]/45",
                  )}
                >
                  <span className="font-mono font-bold">{t.trip_number}</span>
                  <span className="mt-0.5 block text-[9px] opacity-90">
                    {t.status} · {t.member_load_count} loads
                  </span>
                </button>
              ))}
            </div>

            {tripDetailError ? (
              <p className="mb-2 text-[11px] text-[var(--trk-danger)]">
                {tripDetailError}{" "}
                <button type="button" className={btn} onClick={() => focusedTripId != null && void refreshTripDetail(focusedTripId)}>
                  Retry trip
                </button>
              </p>
            ) : null}

            {orientation ? (
              <>
                <article className="mb-3 overflow-hidden rounded-lg border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] shadow-sm">
                  <div className="border-b border-[var(--trk-border)] bg-[var(--trk-surface-2)]/35 px-3 py-2.5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-lg font-bold leading-none tracking-tight text-[var(--trk-text)]">
                            {orientation.trip_number}
                          </span>
                          <span
                            className={clsx(
                              "rounded px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide",
                              tripStatusBadgeClass(orientation.status),
                            )}
                          >
                            {orientation.status}
                          </span>
                        </div>
                        <div className="mt-2 text-[10px] text-[var(--trk-text-muted)]">
                          <span className="font-semibold text-[var(--trk-text)]">{driverLine(orientation)}</span>
                          <span className="mx-1.5 text-[var(--trk-border-strong)]">·</span>
                          <span className="font-mono text-[var(--trk-text)]">{truckLine(orientation)}</span>
                          <span className="mx-1.5">·</span>
                          <span className="font-mono text-[var(--trk-text)]">{trailerLine(orientation)}</span>
                        </div>
                        <div className="mt-1 text-[9px] text-[var(--trk-text-muted)]">
                          {(focusedListItem?.member_load_count ??
                            focusedDetail?.member_loads?.filter((x) => isOpenTripMembership(x)).length ??
                            0) || 0}{" "}
                          loads · <span className="text-[var(--trk-text)]">{routeStrip}</span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-[9px] text-[var(--trk-text-muted)]">
                          <span>
                            Next: <span className="font-semibold text-[var(--trk-heading)]">{nextAct}</span>
                          </span>
                          <span className="rounded border border-dashed border-[var(--trk-border)] px-1 py-0 text-[8px] uppercase">
                            Custody ···
                          </span>
                          <span>Updated {relativeAgo(orientation.updated_at)}</span>
                        </div>
                      </div>
                      <div className="flex max-w-full flex-wrap justify-end gap-1">
                        <button type="button" className={btnOutlineAccent} disabled title="Driver package flow is future in this slice">
                          Send package
                        </button>
                        <button type="button" className={btn} onClick={() => setShowAssignment((v) => !v)}>
                          {showAssignment ? "Hide reassign" : "Reassign"}
                        </button>
                        <button type="button" className={btn} disabled title="··· soon">
                          Unassign
                        </button>
                        <button type="button" className={btn} onClick={() => setShowAddLoad((v) => !v)}>
                          {showAddLoad ? "Hide new load" : "New load"}
                        </button>
                        {focusedDetail && canCancelTrip(focusedDetail) ? (
                          <button
                            type="button"
                            className={btnDanger}
                            onClick={() => {
                              setShowStartConfirm(false);
                              setShowCancelConfirm(true);
                            }}
                          >
                            Cancel
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  {showAssignment && focusedDetail ? (
                    <div className="border-b border-[var(--trk-border)] bg-[var(--trk-bg)]/25 px-3 py-2">
                      <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                        Assignment
                      </div>
                      <SlimAssignmentPanel
                        tripId={focusedTripId!}
                        detail={focusedDetail}
                        assignOk={assignmentEditable(focusedDetail)}
                        onRefreshTripDetail={refreshTripDetail}
                        onRefreshList={() => void fetchTripList()}
                        btnPrimary={btnPrimary}
                      />
                    </div>
                  ) : null}
                </article>

                <section className="mb-3 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2.5 py-2 shadow-sm">
                  <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Execution</div>
                  <p className="mb-1 max-w-2xl text-[9px] leading-snug text-[var(--trk-text-muted)]">
                    <span className="font-semibold text-[var(--trk-text)]">Start Trip</span> begins execution. Driver package tracking is{" "}
                    <span className="font-semibold">future</span> in this slice.
                  </p>
                  {showStartConfirm ? (
                    <div
                      className="mb-2 rounded border border-[var(--trk-warning)] bg-[var(--trk-surface-2)] px-2 py-1.5 text-[9px] leading-snug text-[var(--trk-text)]"
                      role="status"
                    >
                      <p className="whitespace-pre-wrap">{START_TRIP_CONFIRM_MESSAGE}</p>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        <button type="button" className={btn} onClick={() => setShowStartConfirm(false)}>
                          Go back
                        </button>
                        <button
                          type="button"
                          className={btnPrimary}
                          disabled={!focusedDetail || !canStartExecution(focusedDetail)}
                          onClick={async () => {
                            if (!focusedDetail || !canStartExecution(focusedDetail) || focusedTripId == null) return;
                            try {
                              await postTripExecutionSignal(focusedTripId, {
                                source: "dispatcher_manual",
                                reason_note: "Trip Container ops strip",
                              });
                              setShowStartConfirm(false);
                              await refreshTripDetail(focusedTripId);
                              void fetchTripList();
                            } catch (e: unknown) {
                              alert(e instanceof Error ? e.message : "Failed");
                            }
                          }}
                        >
                          Confirm start
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {showCancelConfirm && focusedDetail && canCancelTrip(focusedDetail) ? (
                    <div
                      className="mb-2 rounded border border-[var(--trk-danger)] bg-[var(--trk-surface-2)] px-2 py-1.5 text-[9px] text-[var(--trk-text)]"
                      role="status"
                    >
                      <p>Cancel this planned trip container?</p>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        <button type="button" className={btn} onClick={() => setShowCancelConfirm(false)}>
                          Go back
                        </button>
                        <button
                          type="button"
                          className={btnDanger}
                          onClick={async () => {
                            if (focusedTripId == null) return;
                            try {
                              await cancelTrip(focusedTripId);
                              setShowCancelConfirm(false);
                              await refreshTripDetail(focusedTripId);
                              void fetchTripList();
                            } catch (e: unknown) {
                              alert(e instanceof Error ? e.message : "Cancel failed");
                            }
                          }}
                        >
                          Confirm cancel
                        </button>
                      </div>
                    </div>
                  ) : null}
                  <div className="flex flex-wrap gap-1 rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)]/35 p-1.5">
                    <button type="button" className={btn} disabled title="··· soon">
                      Send Package ··· soon
                    </button>
                    <button
                      type="button"
                      className={btnPrimary}
                      disabled={!focusedDetail || !canStartExecution(focusedDetail)}
                      onClick={() => {
                        if (!focusedDetail || !canStartExecution(focusedDetail)) return;
                        setShowCancelConfirm(false);
                        setShowStartConfirm(true);
                      }}
                    >
                      Start Trip
                    </button>
                    <Link to={OPS.TRIP_DETAIL(focusedTripId!)} className={btn}>
                      Workspace ↗
                    </Link>
                    <button type="button" className={btn} disabled title="··· soon">
                      Complete Trip ··· soon
                    </button>
                    <button type="button" className={btn} disabled title="··· soon">
                      Handoff ··· soon
                    </button>
                  </div>
                  {showAddLoad && focusedTripId != null && focusedDetail ? (
                    <AddLoadPanel
                      tripId={focusedTripId}
                      memOpen={memOpen}
                      onRefreshTripDetail={refreshTripDetail}
                      onRefreshList={() => void fetchTripList()}
                      btn={btn}
                      btnPrimary={btnPrimary}
                    />
                  ) : null}
                </section>

                <div className="mb-2 flex flex-wrap gap-1">
                  <button
                    type="button"
                    className={clsx(
                      "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                      viewMode === "dispatch"
                        ? "border-[var(--trk-accent)] bg-[var(--trk-accent)]/12 text-[var(--trk-accent)]"
                        : "border-transparent text-[var(--trk-text-muted)] hover:border-[var(--trk-border)]",
                    )}
                    onClick={() => setViewMode("dispatch")}
                  >
                    Dispatch view
                  </button>
                  <button
                    type="button"
                    className={clsx(
                      "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                      viewMode === "driver"
                        ? "border-[var(--trk-accent)] bg-[var(--trk-accent)]/12 text-[var(--trk-accent)]"
                        : "border-transparent text-[var(--trk-text-muted)] hover:border-[var(--trk-border)]",
                    )}
                    onClick={() => setViewMode("driver")}
                  >
                    Driver route view
                  </button>
                </div>

                {tripDetailLoading && !focusedDetail ? (
                  <p className="text-[11px] text-[var(--trk-text-muted)]">Loading trip detail…</p>
                ) : null}

                {viewMode === "dispatch" ? (
                  <div className="space-y-3">
                    <TripMergedStopsTimeline members={activeMembers} loadById={loadById} title="Trip route" />
                    <div className="flex items-end justify-between gap-2 border-b border-[var(--trk-border)] pb-1">
                      <h2 className="text-[10px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">Member loads</h2>
                      <span className="text-[8px] text-[var(--trk-text-muted)]">Expand for full workspace</span>
                    </div>
                    {activeMembers.length === 0 ? (
                      <p className="text-[11px] text-[var(--trk-text-muted)]">No active loads on this trip.</p>
                    ) : (
                      activeMembers.map((m) => (
                        <LoadStackBlock
                          key={m.trip_load_id}
                          tripId={focusedTripId!}
                          m={m}
                          memOpen={memOpen}
                          expanded={expandedLoads.has(m.load_id)}
                          onToggleExpand={() => void toggleLoadExpand(m.load_id)}
                          load={loadById.get(m.load_id) ?? null}
                          loadLoading={loadLoading.has(m.load_id)}
                          loadErr={loadError.get(m.load_id) ?? null}
                          expandedStops={expandedStops}
                          onToggleStop={(loadId, stopKey) => {
                            const k = `${loadId}:${stopKey}`;
                            setExpandedStops((prev) => {
                              const n = new Set(prev);
                              if (n.has(k)) n.delete(k);
                              else n.add(k);
                              return n;
                            });
                          }}
                          onRefreshList={() => void fetchTripList()}
                          onDetailRefresh={() => {
                            void refreshTripDetail(focusedTripId!);
                          }}
                          btn={btn}
                          btnDanger={btnDanger}
                        />
                      ))
                    )}
                  </div>
                ) : (
                  <DriverRouteMerged members={activeMembers} loadById={loadById} />
                )}

                <FuturePlaceholderPanels />
              </>
            ) : null}
          </>
              )}
            </div>
            <CommsCockpitPlaceholder
              tab={commsTab}
              onTab={setCommsTab}
              tripLabel={focusedListItem?.trip_number ?? focusedDetail?.trip_number ?? "—"}
              driverHint={orientation ? driverLine(orientation) : undefined}
            />
          </div>
        )}
      </main>
    </div>
  );
}
