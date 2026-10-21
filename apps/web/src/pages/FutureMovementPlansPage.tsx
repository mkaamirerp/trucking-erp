import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Button from "@/components/Button";
import {
  cancelFutureMovementPlan,
  convertFutureMovementPlan,
  getFutureMovementPlan,
  listFutureMovementPlans,
  listTerminals,
  updateFutureMovementPlan,
  type FutureMovementPlan,
  type FutureMovementPlanLine,
  listDrivers,
  listTrucks,
  listTrailers,
  fetchTerminalPoolLoadsForFmp,
} from "@/api";
import { OPS } from "@/routes";

type FleetDriver = { id: number; first_name: string; last_name: string };
type FleetUnit = { id: number; unit_number?: string | null };

function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInput(v: string): string | null {
  if (!v.trim()) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export default function FutureMovementPlansPage() {
  const { planId } = useParams<{ planId?: string }>();
  const navigate = useNavigate();
  const [list, setList] = useState<FutureMovementPlan[]>([]);
  const [detail, setDetail] = useState<FutureMovementPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [terminals, setTerminals] = useState<{ id: number; name: string }[]>([]);
  const [drivers, setDrivers] = useState<FleetDriver[]>([]);
  const [trucks, setTrucks] = useState<FleetUnit[]>([]);
  const [trailers, setTrailers] = useState<FleetUnit[]>([]);

  const [pickupTerminalId, setPickupTerminalId] = useState<number | "">("");
  const [plannedStart, setPlannedStart] = useState("");
  const [driverId, setDriverId] = useState<number | "">("");
  const [truckId, setTruckId] = useState<number | "">("");
  const [trailerId, setTrailerId] = useState<number | "">("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<FutureMovementPlanLine[]>([]);
  const [poolSelection, setPoolSelection] = useState<Record<number, boolean>>({});

  const editable = detail?.status === "unassigned" || detail?.status === "draft";

  const refreshList = useCallback(() => {
    setLoading(true);
    listFutureMovementPlans({ status: "unassigned", page: 1, size: 100 })
      .then((res) => setList(res.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const loadDetail = useCallback((id: number) => {
    setLoading(true);
    getFutureMovementPlan(id)
      .then((p) => {
        setDetail(p);
        setPickupTerminalId(p.pickup_terminal_id ?? "");
        setPlannedStart(toLocalInput(p.planned_start_at));
        setDriverId(p.driver_id ?? "");
        setTruckId(p.truck_id ?? "");
        setTrailerId(p.trailer_id ?? "");
        setNotes(p.notes ?? "");
        setLines(p.lines || []);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    listTerminals().then((r) => setTerminals(r.items || []));
    listDrivers().then((rows) => setDrivers(rows || []));
    listTrucks({ page: 1, size: 200 }).then((r) => setTrucks(r.items || []));
    listTrailers({ page: 1, size: 200 }).then((r) => setTrailers(r.items || []));
  }, []);

  useEffect(() => {
    if (!planId) {
      refreshList();
      return;
    }
    loadDetail(Number(planId));
  }, [planId, refreshList, loadDetail]);

  const poolTerminalId = pickupTerminalId === "" ? null : Number(pickupTerminalId);

  const loadTerminalPool = async () => {
    if (!poolTerminalId) {
      setError("Select a pickup terminal to load yard pool.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const items = await fetchTerminalPoolLoadsForFmp(poolTerminalId);
      const next: Record<number, boolean> = { ...poolSelection };
      for (const row of items) {
        if (!lines.some((l) => l.load_id === row.load_id)) {
          next[row.load_id] = false;
        }
      }
      setPoolSelection(next);
      setMessage(`Yard pool: ${items.length} eligible load(s) at terminal.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load terminal pool");
    } finally {
      setBusy(false);
    }
  };

  const addSelectedPoolLoads = () => {
    const toAdd = Object.entries(poolSelection)
      .filter(([, on]) => on)
      .map(([id]) => Number(id));
    const existing = new Set(lines.map((l) => l.load_id));
    const merged = [...lines];
    for (const lid of toAdd) {
      if (!existing.has(lid)) {
        merged.push({ load_id: lid, sequence_hint: merged.length + 1 });
        existing.add(lid);
      }
    }
    setLines(merged);
    setMessage(`Added ${toAdd.length} load(s) to manifest.`);
  };

  const savePlan = async () => {
    if (!detail || !editable) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateFutureMovementPlan(detail.id, {
        pickup_terminal_id: poolTerminalId,
        planned_start_at: fromLocalInput(plannedStart),
        driver_id: driverId === "" ? null : driverId,
        truck_id: truckId === "" ? null : truckId,
        trailer_id: trailerId === "" ? null : trailerId,
        notes: notes || null,
        lines: lines.map((l, i) => ({
          load_id: l.load_id,
          sequence_hint: l.sequence_hint ?? i + 1,
          inbound_trip_id: l.inbound_trip_id ?? null,
        })),
        concurrency_version: detail.concurrency_version,
      });
      setDetail(updated);
      setLines(updated.lines || []);
      setMessage("Plan saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const convertPlan = async () => {
    if (!detail || !editable) return;
    if (driverId === "") {
      setError("Assign a driver before converting to a numbered trip.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await updateFutureMovementPlan(detail.id, {
        pickup_terminal_id: poolTerminalId,
        planned_start_at: fromLocalInput(plannedStart),
        driver_id: driverId as number,
        truck_id: truckId === "" ? null : truckId,
        trailer_id: trailerId === "" ? null : trailerId,
        notes: notes || null,
        lines: lines.map((l, i) => ({
          load_id: l.load_id,
          sequence_hint: l.sequence_hint ?? i + 1,
          inbound_trip_id: l.inbound_trip_id ?? null,
        })),
        concurrency_version: detail.concurrency_version,
      });
      setDetail(updated);
      const trip = await convertFutureMovementPlan(updated.id, {
        driver_id: driverId as number,
        truck_id: truckId === "" ? null : truckId,
        trailer_id: trailerId === "" ? null : trailerId,
        concurrency_version: updated.concurrency_version,
        conversion_idempotency_key: `ui-fmp-${updated.id}`,
      });
      navigate(OPS.TRIP_DETAIL(trip.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Convert failed");
    } finally {
      setBusy(false);
    }
  };

  const onCancel = async () => {
    if (!detail) return;
    setBusy(true);
    try {
      await cancelFutureMovementPlan(detail.id, detail.concurrency_version);
      navigate("/dispatch/future-plans");
      refreshList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
    } finally {
      setBusy(false);
    }
  };

  const manifestSummary = useMemo(
    () => lines.map((l) => l.load_number || `Load ${l.load_id}`).join(", "),
    [lines],
  );

  if (planId && detail) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 p-4">
        <Link to="/dispatch/future-plans" className="text-xs text-[var(--trk-text-muted)] hover:underline">
          ← Unassigned plans
        </Link>
        <h1 className="text-lg font-semibold">Future movement plan #{detail.id}</h1>
        <p className="text-sm text-[var(--trk-text-muted)]">
          Status: <span className="font-mono">{detail.status}</span>
          {detail.converted_trip_id ? (
            <>
              {" "}
              · Converted trip:{" "}
              <Link to={OPS.TRIP_DETAIL(detail.converted_trip_id)} className="underline">
                {detail.converted_trip_number || detail.converted_trip_id}
              </Link>
            </>
          ) : null}
        </p>
        {editable ? (
          <div className="space-y-3 rounded border border-[var(--trk-border)] p-3 text-[12px]">
            <label className="block">
              Pickup terminal
              <select
                className="mt-1 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
                value={pickupTerminalId}
                onChange={(e) => setPickupTerminalId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">—</option>
                {terminals.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </label>
            <label className="block">
              Planned start
              <input
                type="datetime-local"
                className="mt-1 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
                value={plannedStart}
                onChange={(e) => setPlannedStart(e.target.value)}
              />
            </label>
            <div className="grid gap-2 sm:grid-cols-3">
              <label className="block">
                Driver
                <select
                  className="mt-1 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
                  value={driverId}
                  onChange={(e) => setDriverId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">—</option>
                  {drivers.map((d) => (
                    <option key={d.id} value={d.id}>{d.first_name} {d.last_name}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                Truck
                <select
                  className="mt-1 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
                  value={truckId}
                  onChange={(e) => setTruckId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">—</option>
                  {trucks.map((t) => (
                    <option key={t.id} value={t.id}>{t.unit_number || t.id}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                Trailer
                <select
                  className="mt-1 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
                  value={trailerId}
                  onChange={(e) => setTrailerId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">—</option>
                  {trailers.map((t) => (
                    <option key={t.id} value={t.id}>{t.unit_number || t.id}</option>
                  ))}
                </select>
              </label>
            </div>
            <label className="block">
              Notes
              <textarea
                className="mt-1 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
            <div>
              <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">Manifest ({lines.length} loads)</span>
                <div className="flex gap-2">
                  <Button type="button" variant="secondary" disabled={busy} onClick={() => void loadTerminalPool()}>
                    Load terminal pool
                  </Button>
                  <Button type="button" variant="secondary" disabled={busy} onClick={addSelectedPoolLoads}>
                    Add selected from pool
                  </Button>
                </div>
              </div>
              <ul className="divide-y divide-[var(--trk-border)] rounded border border-[var(--trk-border)]">
                {lines.map((ln, idx) => (
                  <li key={`${ln.load_id}-${idx}`} className="flex items-center justify-between px-2 py-1">
                    <span>
                      #{ln.sequence_hint ?? idx + 1} · {ln.load_number || `Load ${ln.load_id}`}
                      {ln.inbound_trip_id ? ` (inbound ${ln.inbound_trip_id})` : ""}
                    </span>
                    <button
                      type="button"
                      className="text-red-700 hover:underline"
                      onClick={() => setLines(lines.filter((_, i) => i !== idx))}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
              {Object.keys(poolSelection).length > 0 ? (
                <div className="mt-2 max-h-40 overflow-y-auto rounded border border-dashed border-[var(--trk-border)] p-2">
                  {Object.keys(poolSelection).map((id) => {
                    const lid = Number(id);
                    if (lines.some((l) => l.load_id === lid)) return null;
                    return (
                      <label key={lid} className="flex items-center gap-2 py-0.5">
                        <input
                          type="checkbox"
                          checked={poolSelection[lid] || false}
                          onChange={(e) => setPoolSelection({ ...poolSelection, [lid]: e.target.checked })}
                        />
                        Load {lid}
                      </label>
                    );
                  })}
                </div>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button type="button" disabled={busy} onClick={() => void savePlan()}>
                Save plan
              </Button>
              <Button type="button" disabled={busy} onClick={() => void convertPlan()}>
                Assign driver & convert to trip
              </Button>
              <Button type="button" variant="secondary" disabled={busy} onClick={() => void onCancel()}>
                Cancel plan
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm">Manifest: {manifestSummary || "—"}</p>
        )}
        {message ? <p className="text-xs text-green-800">{message}</p> : null}
        {error ? <p className="text-xs text-red-700">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Unassigned future movement plans</h1>
      <p className="text-sm text-[var(--trk-text-muted)]">
        Pre-trip follow-up dispatch. Trip numbers are minted only when a plan is converted.
      </p>
      {loading ? <p className="text-sm">Loading…</p> : null}
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <ul className="divide-y divide-[var(--trk-border)] rounded border border-[var(--trk-border)]">
        {list.map((p) => (
          <li key={p.id} className="flex items-center justify-between px-3 py-2 text-sm">
            <span>
              Plan #{p.id} · {p.lines.length} load(s)
              {p.planned_start_at ? ` · ${new Date(p.planned_start_at).toLocaleString()}` : ""}
            </span>
            <Link to={`/dispatch/future-plans/${p.id}`} className="font-semibold hover:underline">
              Edit →
            </Link>
          </li>
        ))}
        {!loading && list.length === 0 ? (
          <li className="px-3 py-4 text-sm text-[var(--trk-text-muted)]">No unassigned plans.</li>
        ) : null}
      </ul>
    </div>
  );
}
