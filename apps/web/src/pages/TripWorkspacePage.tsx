/**
 * Trip workspace: planned container, member loads, and cancellation controls.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  addLoadToTrip,
  cancelTrip,
  getTrip,
  listDrivers,
  listLoads,
  listTrailers,
  listTrucks,
  removeLoadFromTrip,
  updateTripAssignment,
  type Driver,
  type Load,
  type Trailer,
  type TripDetail,
  type TripMemberLoad,
  type Truck,
} from "@/api";
import { OPS } from "@/routes";

function formatMoney(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

function formatAddTripLoadError(err: unknown): string {
  if (!(err instanceof Error)) return "Could not add load to trip.";
  const raw = err.message?.trim() || "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const detail = parsed.detail;
    if (typeof detail === "string") {
      if (/^load not found$/i.test(detail.trim())) return "Load not found.";
      if (/^trip not found$/i.test(detail.trim())) return "Trip not found.";
    }
    if (detail && typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const code = (detail as { code?: string }).code;
      switch (code) {
        case "TRIP_CANCELLED":
          return "This trip is cancelled. You can't add loads.";
        case "LOAD_ACTIVE_ON_OTHER_TRIP":
          return "This load is already on another active trip.";
        case "DUPLICATE_TRIP_LOAD_MEMBERSHIP":
          return "This load is already on this trip.";
        default:
          break;
      }
      const msg =
        typeof (detail as { detail?: unknown }).detail === "string"
          ? (detail as { detail: string }).detail
          : null;
      if (msg) return msg;
    }
  } catch {
    /* use raw */
  }
  if (raw.length > 0 && raw.length < 400) return raw;
  return "Could not add load to trip.";
}

function formatRemoveTripLoadError(err: unknown): string {
  if (!(err instanceof Error)) return "Could not remove load from trip.";
  const raw = err.message?.trim() || "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const detail = parsed.detail;
    if (typeof detail === "string") {
      if (/^trip not found$/i.test(detail.trim())) return "Trip not found.";
    }
    if (detail && typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const code = (detail as { code?: string }).code;
      switch (code) {
        case "TRIP_CANCELLED":
          return "This trip is cancelled. You can't remove loads.";
        case "TRIP_LOAD_NOT_FOUND":
          return "This load is not active on this trip.";
        default:
          break;
      }
      const msg =
        typeof (detail as { detail?: unknown }).detail === "string"
          ? (detail as { detail: string }).detail
          : null;
      if (msg) return msg;
    }
  } catch {
    /* use raw */
  }
  if (raw.length > 0 && raw.length < 400) return raw;
  return "Could not remove load from trip.";
}

function formatAssignmentError(err: unknown): string {
  if (!(err instanceof Error)) return "Could not save assignment.";
  const raw = err.message?.trim() || "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const detail = parsed.detail;
    if (typeof detail === "string") {
      if (/^trip not found$/i.test(detail.trim())) return "Trip not found.";
    }
    if (detail && typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const code = (detail as { code?: string }).code;
      if (code === "TRIP_CANCELLED") return "This trip is cancelled. Assignment cannot be changed.";
      const msg =
        typeof (detail as { detail?: unknown }).detail === "string"
          ? (detail as { detail: string }).detail
          : null;
      if (msg) return msg;
    }
  } catch {
    /* use raw */
  }
  if (raw.length > 0 && raw.length < 400) return raw;
  return "Could not save assignment.";
}

function formatCancelTripError(err: unknown): string {
  if (!(err instanceof Error)) return "Could not cancel trip.";
  const raw = err.message?.trim() || "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const detail = parsed.detail;
    if (typeof detail === "string") {
      if (/^trip not found$/i.test(detail.trim())) return "Trip not found.";
    }
    if (detail && typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const code = (detail as { code?: string }).code;
      if (code === "TRIP_ALREADY_CANCELLED") return "This trip is already cancelled.";
      const msg =
        typeof (detail as { detail?: unknown }).detail === "string"
          ? (detail as { detail: string }).detail
          : null;
      if (msg) return msg;
    }
  } catch {
    /* use raw */
  }
  if (raw.length > 0 && raw.length < 400) return raw;
  return "Could not cancel trip.";
}

/** Planned trip and not cancelled — same gate for Add load and Remove (3G/3H). */
function isPlannedTripOpenForMembershipActions(trip: TripDetail): boolean {
  return (trip.status || "").toLowerCase() === "planned" && trip.cancelled_at == null;
}

/** Cancel trip control — explicit planned + open (matches backend planned cancel). */
function isPlannedTripOpenForCancel(trip: TripDetail): boolean {
  return trip.status === "planned" && trip.cancelled_at == null;
}

function pickerBrokerLine(row: Load): string {
  const snap = (row.broker_name_snapshot || "").trim();
  const fromRel = (row.broker?.name || "").trim();
  const name = snap || fromRel;
  return name || "—";
}

export default function TripWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const tripId = Number(id);
  const navigate = useNavigate();
  const [trip, setTrip] = useState<TripDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [addLoadIdInput, setAddLoadIdInput] = useState("");
  const [addLoadBusy, setAddLoadBusy] = useState(false);
  const [addLoadError, setAddLoadError] = useState<string | null>(null);
  const [removingLoadId, setRemovingLoadId] = useState<number | null>(null);
  const [removeLoadError, setRemoveLoadError] = useState<string | null>(null);
  const [loadSearchQuery, setLoadSearchQuery] = useState("");
  const [loadSearchResults, setLoadSearchResults] = useState<Load[]>([]);
  const [loadSearchBusy, setLoadSearchBusy] = useState(false);
  const [loadSearchError, setLoadSearchError] = useState<string | null>(null);
  const [cancelTripBusy, setCancelTripBusy] = useState(false);
  const [cancelTripError, setCancelTripError] = useState<string | null>(null);
  const [assignPickBusy, setAssignPickBusy] = useState(false);
  const [assignSaveBusy, setAssignSaveBusy] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [assignDrivers, setAssignDrivers] = useState<Driver[]>([]);
  const [assignTrucks, setAssignTrucks] = useState<Truck[]>([]);
  const [assignTrailers, setAssignTrailers] = useState<Trailer[]>([]);
  const [draftDriverId, setDraftDriverId] = useState("");
  const [draftTruckId, setDraftTruckId] = useState("");
  const [draftTrailerId, setDraftTrailerId] = useState("");

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

  useEffect(() => {
    setAddLoadError(null);
    setAddLoadIdInput("");
    setRemoveLoadError(null);
    setRemovingLoadId(null);
    setLoadSearchQuery("");
    setLoadSearchResults([]);
    setLoadSearchError(null);
    setCancelTripError(null);
    setCancelTripBusy(false);
    setAssignError(null);
    setAssignPickBusy(false);
    setAssignSaveBusy(false);
    setAssignDrivers([]);
    setAssignTrucks([]);
    setAssignTrailers([]);
    setDraftDriverId("");
    setDraftTruckId("");
    setDraftTrailerId("");
  }, [tripId]);

  const assignmentEditable = Boolean(trip && trip.cancelled_at == null);

  useEffect(() => {
    if (!trip) return;
    setDraftDriverId(trip.driver_id != null ? String(trip.driver_id) : "");
    setDraftTruckId(trip.truck_id != null ? String(trip.truck_id) : "");
    setDraftTrailerId(trip.trailer_id != null ? String(trip.trailer_id) : "");
  }, [trip?.id, trip?.driver_id, trip?.truck_id, trip?.trailer_id]);

  useEffect(() => {
    if (!assignmentEditable) return;
    let cancelled = false;
    void (async () => {
      setAssignPickBusy(true);
      setAssignError(null);
      try {
        const [dRes, tRes, rRes] = await Promise.all([
          listDrivers({ limit: 200 }),
          listTrucks({ page: 1, size: 200 }),
          listTrailers({ page: 1, size: 200 }),
        ]);
        if (!cancelled) {
          setAssignDrivers(dRes);
          setAssignTrucks(tRes.items);
          setAssignTrailers(rRes.items);
        }
      } catch (e: unknown) {
        if (!cancelled) setAssignError(e instanceof Error ? e.message : "Could not load drivers/trucks/trailers.");
      } finally {
        if (!cancelled) setAssignPickBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [assignmentEditable, tripId]);

  const clearPickerSearch = useCallback(() => {
    setLoadSearchQuery("");
    setLoadSearchResults([]);
    setLoadSearchError(null);
  }, []);

  const runLoadSearch = useCallback(async () => {
    const q = loadSearchQuery.trim();
    if (!q) return;
    setLoadSearchBusy(true);
    setLoadSearchError(null);
    try {
      const p = await listLoads({ search: q, page: 1, size: 20 });
      setLoadSearchResults(p.items);
    } catch (e: unknown) {
      setLoadSearchError(e instanceof Error ? e.message : "Search failed.");
    } finally {
      setLoadSearchBusy(false);
    }
  }, [loadSearchQuery]);

  const onAddLoadFromPicker = useCallback(async (loadId: number) => {
    if (!Number.isFinite(tripId)) return;
    setAddLoadBusy(true);
    setAddLoadError(null);
    try {
      const updated = await addLoadToTrip(tripId, { load_id: loadId });
      setTrip(updated);
      clearPickerSearch();
      setAddLoadError(null);
    } catch (e) {
      setAddLoadError(formatAddTripLoadError(e));
    } finally {
      setAddLoadBusy(false);
    }
  }, [tripId, clearPickerSearch]);

  const onAddLoadToTrip = useCallback(async () => {
    if (!Number.isFinite(tripId)) return;
    const loadId = Number(addLoadIdInput.trim());
    if (!Number.isFinite(loadId) || loadId < 1) {
      setAddLoadError("Enter a valid load ID.");
      return;
    }
    setAddLoadBusy(true);
    setAddLoadError(null);
    try {
      const updated = await addLoadToTrip(tripId, { load_id: loadId });
      setTrip(updated);
      setAddLoadIdInput("");
      clearPickerSearch();
      setAddLoadError(null);
    } catch (e) {
      setAddLoadError(formatAddTripLoadError(e));
    } finally {
      setAddLoadBusy(false);
    }
  }, [tripId, addLoadIdInput, clearPickerSearch]);

  const activeMemberLoads = useMemo(
    () => (trip?.member_loads ?? []).filter((m: TripMemberLoad) => m.removed_at == null),
    [trip?.member_loads],
  );

  const historicalMemberLoads = useMemo(() => {
    const rows = (trip?.member_loads ?? []).filter((m: TripMemberLoad) => m.removed_at != null);
    return [...rows].sort((a, b) => {
      const ta = a.removed_at ? new Date(a.removed_at).getTime() : 0;
      const tb = b.removed_at ? new Date(b.removed_at).getTime() : 0;
      return tb - ta;
    });
  }, [trip?.member_loads]);

  const onRemoveLoadFromTrip = useCallback(
    async (loadId: number, loadLabel: string) => {
      if (!Number.isFinite(tripId)) return;
      if (
        !window.confirm(`Remove load ${loadLabel} (ID ${loadId}) from this trip? This does not delete the commercial load.`)
      ) {
        return;
      }
      setRemovingLoadId(loadId);
      setRemoveLoadError(null);
      try {
        const updated = await removeLoadFromTrip(tripId, loadId);
        setTrip(updated);
      } catch (e) {
        setRemoveLoadError(formatRemoveTripLoadError(e));
      } finally {
        setRemovingLoadId(null);
      }
    },
    [tripId],
  );

  const onSaveAssignment = useCallback(async () => {
    if (!Number.isFinite(tripId) || !trip) return;
    setAssignSaveBusy(true);
    setAssignError(null);
    try {
      const driver_id = draftDriverId.trim() === "" ? null : Number(draftDriverId);
      const truck_id = draftTruckId.trim() === "" ? null : Number(draftTruckId);
      const trailer_id = draftTrailerId.trim() === "" ? null : Number(draftTrailerId);
      if (
        (driver_id != null && !Number.isFinite(driver_id)) ||
        (truck_id != null && !Number.isFinite(truck_id)) ||
        (trailer_id != null && !Number.isFinite(trailer_id))
      ) {
        setAssignError("Select valid driver, truck, and trailer, or clear each dropdown.");
        return;
      }
      const updated = await updateTripAssignment(tripId, { driver_id, truck_id, trailer_id });
      setTrip(updated);
    } catch (e: unknown) {
      setAssignError(formatAssignmentError(e));
    } finally {
      setAssignSaveBusy(false);
    }
  }, [tripId, trip, draftDriverId, draftTruckId, draftTrailerId]);

  const onCancelPlannedTrip = useCallback(async () => {
    if (!Number.isFinite(tripId)) return;
    if (
      !window.confirm(
        "Cancel this trip container?\n\nThis only cancels the operational trip container. Loads are not deleted. Commercial load status is not changed.\n\nContinue?",
      )
    ) {
      return;
    }
    setCancelTripBusy(true);
    setCancelTripError(null);
    try {
      const updated = await cancelTrip(tripId);
      setTrip(updated);
    } catch (e) {
      setCancelTripError(formatCancelTripError(e));
    } finally {
      setCancelTripBusy(false);
    }
  }, [tripId]);

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
              <div className="font-mono text-[11px] text-[var(--trk-text-muted)]">Operational trip workspace</div>
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
          {!loading && trip && isPlannedTripOpenForCancel(trip) ? (
            <div className="flex flex-col items-end gap-1">
              <button
                type="button"
                disabled={cancelTripBusy}
                onClick={() => void onCancelPlannedTrip()}
                className="rounded-md border border-red-300/80 bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-red-800 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {cancelTripBusy ? "Cancelling…" : "Cancel Trip"}
              </button>
              {cancelTripError ? <p className="max-w-xs text-right text-[10px] text-red-700">{cancelTripError}</p> : null}
            </div>
          ) : null}
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
              <h2 className="text-sm font-semibold text-[var(--trk-text)]">Equipment & assignment</h2>
              <p className="mt-2 text-[11px] text-[var(--trk-text-muted)]">
                Trip movement assignment is owned here — not via Load.status. All three resources must be set for the trip
                to move to <span className="font-medium text-[var(--trk-text)]">assigned</span>.
              </p>
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

              {assignmentEditable ? (
                <div className="mt-4 space-y-3 border-t border-[var(--trk-border)] pt-4">
                  <div className="text-[11px] font-medium text-[var(--trk-text-muted)]">Update assignment</div>
                  {assignPickBusy ? (
                    <p className="text-[11px] text-[var(--trk-text-muted)]">Loading drivers/trucks/trailers…</p>
                  ) : null}
                  <div className="grid max-w-xl gap-2 sm:grid-cols-3">
                    <label className="flex flex-col gap-1 text-[11px]">
                      <span className="text-[var(--trk-text-muted)]">Driver</span>
                      <select
                        value={draftDriverId}
                        onChange={(e) => setDraftDriverId(e.target.value)}
                        disabled={assignSaveBusy}
                        className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1.5 text-sm text-[var(--trk-text)]"
                      >
                        <option value="">— None —</option>
                        {assignDrivers.map((d) => (
                          <option key={d.id} value={String(d.id)}>
                            #{d.id} {d.first_name} {d.last_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1 text-[11px]">
                      <span className="text-[var(--trk-text-muted)]">Truck</span>
                      <select
                        value={draftTruckId}
                        onChange={(e) => setDraftTruckId(e.target.value)}
                        disabled={assignSaveBusy}
                        className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1.5 text-sm text-[var(--trk-text)]"
                      >
                        <option value="">— None —</option>
                        {assignTrucks.map((t) => (
                          <option key={t.id} value={String(t.id)}>
                            #{t.id} {t.unit_number}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1 text-[11px]">
                      <span className="text-[var(--trk-text-muted)]">Trailer</span>
                      <select
                        value={draftTrailerId}
                        onChange={(e) => setDraftTrailerId(e.target.value)}
                        disabled={assignSaveBusy}
                        className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1.5 text-sm text-[var(--trk-text)]"
                      >
                        <option value="">— None —</option>
                        {assignTrailers.map((r) => (
                          <option key={r.id} value={String(r.id)}>
                            #{r.id} {r.unit_number}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={assignSaveBusy || assignPickBusy}
                      onClick={() => void onSaveAssignment()}
                      className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-heading)] hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {assignSaveBusy ? "Saving…" : "Save assignment"}
                    </button>
                  </div>
                  {assignError ? <p className="text-[11px] text-red-700">{assignError}</p> : null}
                </div>
              ) : null}
            </section>

            <section className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] p-5">
              <h2 className="text-sm font-semibold text-[var(--trk-text)]">Member loads</h2>
              <p className="mt-2 text-sm text-[var(--trk-text-muted)]">
                Trip is the operational container. <span className="font-medium text-[var(--trk-text)]">Active</span> loads
                are listed below; ended memberships appear under{" "}
                <span className="font-medium text-[var(--trk-text)]">Previously on this trip</span> when present. Open a load
                for rate, broker, and document work — commercial records are not deleted when a load leaves a trip.
              </p>
              {isPlannedTripOpenForMembershipActions(trip) ? (
                <div className="mt-4 flex flex-col gap-3">
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[11px] font-medium text-[var(--trk-text-muted)]">Search loads</span>
                    <div className="flex flex-wrap items-end gap-2">
                      <input
                        type="search"
                        autoComplete="off"
                        value={loadSearchQuery}
                        onChange={(e) => {
                          setLoadSearchQuery(e.target.value);
                          if (loadSearchError) setLoadSearchError(null);
                          if (addLoadError) setAddLoadError(null);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void runLoadSearch();
                          }
                        }}
                        disabled={addLoadBusy || loadSearchBusy}
                        placeholder="Load #, broker, or reference"
                        className="min-w-[12rem] max-w-md flex-1 rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1.5 text-sm text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)] focus:border-amber-500 focus:outline-none disabled:opacity-50"
                      />
                      <button
                        type="button"
                        disabled={addLoadBusy || loadSearchBusy || !loadSearchQuery.trim()}
                        onClick={() => void runLoadSearch()}
                        className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-heading)] hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {loadSearchBusy ? "Searching…" : "Search"}
                      </button>
                    </div>
                    {loadSearchError ? <p className="text-[11px] text-red-700">{loadSearchError}</p> : null}
                  </div>
                  {loadSearchResults.length > 0 ? (
                    <ul className="max-h-60 overflow-y-auto divide-y divide-[var(--trk-border)] rounded-lg border border-[var(--trk-border)] text-[11px]">
                      {loadSearchResults.map((row) => (
                        <li key={row.id} className="flex flex-wrap items-start justify-between gap-2 px-3 py-2">
                          <div className="min-w-0 space-y-0.5">
                            <div className="font-medium text-[var(--trk-text)]">
                              #{row.id} · {row.load_number || "—"}{" "}
                              <span className="font-normal text-[var(--trk-text-muted)]">({row.status})</span>
                            </div>
                            <div className="text-[var(--trk-text-muted)]">{pickerBrokerLine(row)}</div>
                            {row.broker_load_reference ? (
                              <div className="text-[var(--trk-text-muted)]">Ref {row.broker_load_reference}</div>
                            ) : null}
                            {row.active_trip_id != null ? (
                              <div className="text-[10px] italic text-amber-800/80">
                                Trip mirror hint: active_trip_id {row.active_trip_id}
                              </div>
                            ) : null}
                          </div>
                          <button
                            type="button"
                            disabled={addLoadBusy}
                            onClick={() => void onAddLoadFromPicker(row.id)}
                            className="shrink-0 rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-heading)] hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {addLoadBusy ? "…" : "Add"}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <div className="border-t border-[var(--trk-border)] pt-3">
                    <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                      Add by ID
                    </div>
                    <div className="flex flex-wrap items-end gap-2">
                      <label className="flex flex-col gap-0.5 text-[11px] text-[var(--trk-text-muted)]">
                        Load ID
                        <input
                          type="text"
                          inputMode="numeric"
                          autoComplete="off"
                          value={addLoadIdInput}
                          onChange={(e) => {
                            setAddLoadIdInput(e.target.value);
                            if (addLoadError) setAddLoadError(null);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void onAddLoadToTrip();
                            }
                          }}
                          disabled={addLoadBusy}
                          placeholder="e.g. 526"
                          className="w-32 rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1.5 text-sm text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)] focus:border-amber-500 focus:outline-none disabled:opacity-50"
                        />
                      </label>
                      <button
                        type="button"
                        disabled={addLoadBusy}
                        onClick={() => void onAddLoadToTrip()}
                        className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-heading)] hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {addLoadBusy ? "Adding…" : "Add load"}
                      </button>
                    </div>
                  </div>
                  {addLoadError ? <p className="text-[11px] text-red-700">{addLoadError}</p> : null}
                </div>
              ) : null}
              {removeLoadError ? <p className="mt-3 text-[11px] text-red-700">{removeLoadError}</p> : null}
              {activeMemberLoads.length === 0 ? (
                <p className="mt-4 text-sm italic text-[var(--trk-text-muted)]">
                  {trip.cancelled_at != null
                    ? "No active loads. Memberships were ended when the trip was cancelled. Commercial loads are unchanged."
                    : "No loads on this trip yet."}
                </p>
              ) : (
                <ul className="mt-4 divide-y divide-[var(--trk-border)] rounded-lg border border-[var(--trk-border)]">
                  {activeMemberLoads.map((m) => (
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
                      <div className="flex shrink-0 flex-col items-end gap-1 text-right text-xs text-[var(--trk-text-muted)]">
                        <div>{m.status_within_trip}</div>
                        <div>
                          {formatMoney(m.rate)} / {formatMoney(m.customer_rate)}
                        </div>
                        {isPlannedTripOpenForMembershipActions(trip) ? (
                          <button
                            type="button"
                            disabled={removingLoadId === m.load_id}
                            onClick={() => void onRemoveLoadFromTrip(m.load_id, m.load_number || `#${m.load_id}`)}
                            className="mt-1 rounded border border-red-200/80 bg-[var(--trk-surface)] px-2 py-0.5 text-[10px] font-semibold text-red-800 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {removingLoadId === m.load_id ? "Removing…" : "Remove"}
                          </button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {historicalMemberLoads.length > 0 ? (
                <div className="mt-6 border-t border-[var(--trk-border)] pt-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                    Previously on this trip
                  </h3>
                  <ul className="mt-3 divide-y divide-[var(--trk-border)] rounded-lg border border-[var(--trk-border)] border-dashed bg-[var(--trk-bg)]/40 opacity-95">
                    {historicalMemberLoads.map((m) => (
                      <li key={m.trip_load_id} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
                        <div className="min-w-0">
                          <Link
                            to={OPS.LOAD_DETAIL(m.load_id)}
                            className="text-sm font-medium text-[var(--trk-text-muted)] hover:text-[var(--trk-heading)] hover:underline"
                          >
                            {m.load_number || `Load #${m.load_id}`}
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
                        <div className="shrink-0 text-right text-[11px] text-[var(--trk-text-muted)]">
                          <div>{m.status_within_trip}</div>
                          {m.removed_at ? (
                            <div className="mt-1">Removed {new Date(m.removed_at).toLocaleString()}</div>
                          ) : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
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
