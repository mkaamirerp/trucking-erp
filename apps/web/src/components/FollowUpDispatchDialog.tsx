import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "@/components/Button";
import {
  convertFutureMovementPlan,
  createFutureMovementPlan,
  listTerminals,
  type Load,
  type TerminalOption,
} from "@/api";
import { OPS } from "@/routes";

type Props = {
  load: Load;
  drivers: { id: number; first_name: string; last_name: string }[];
  trucks: { id: number; unit_number?: string | null }[];
  trailers: { id: number; unit_number?: string | null }[];
  onClose: () => void;
  onSaved: () => void;
};

export default function FollowUpDispatchDialog({
  load,
  drivers,
  trucks,
  trailers,
  onClose,
  onSaved,
}: Props) {
  const navigate = useNavigate();
  const [terminals, setTerminals] = useState<TerminalOption[]>([]);
  const [terminalId, setTerminalId] = useState<number | "">("");
  const [plannedDate, setPlannedDate] = useState("");
  const [driverId, setDriverId] = useState<number | "">("");
  const [truckId, setTruckId] = useState<number | "">("");
  const [trailerId, setTrailerId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTerminals()
      .then((res) => setTerminals(res.items || []))
      .catch(() => setTerminals([]));
  }, []);

  const line = {
    load_id: load.id,
    inbound_trip_id: load.active_trip_id ?? undefined,
  };

  const baseBody = () => ({
    origin_kind: "follow_up_inbound",
    pickup_terminal_id: terminalId === "" ? null : terminalId,
    planned_start_at: plannedDate ? new Date(plannedDate).toISOString() : null,
    driver_id: driverId === "" ? null : driverId,
    truck_id: truckId === "" ? null : truckId,
    trailer_id: trailerId === "" ? null : trailerId,
    lines: [line],
  });

  const saveUnassigned = async () => {
    setBusy(true);
    setError(null);
    try {
      await createFutureMovementPlan(baseBody());
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save plan");
    } finally {
      setBusy(false);
    }
  };

  const assignAndSave = async () => {
    if (driverId === "") {
      setError("Driver is required to assign and create a trip.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const plan = await createFutureMovementPlan({
        ...baseBody(),
        driver_id: driverId,
      });
      const trip = await convertFutureMovementPlan(plan.id, {
        driver_id: driverId as number,
        truck_id: truckId === "" ? null : truckId,
        trailer_id: trailerId === "" ? null : trailerId,
        concurrency_version: plan.concurrency_version,
        conversion_idempotency_key: `fmp-${plan.id}-convert`,
      });
      onSaved();
      onClose();
      navigate(OPS.TRIP_DETAIL(trip.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to convert plan");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4 shadow-lg"
        role="dialog"
        aria-labelledby="follow-up-dispatch-title"
      >
        <h2 id="follow-up-dispatch-title" className="text-sm font-semibold text-[var(--trk-heading)]">
          Follow-up dispatch — Load {load.load_number || load.id}
        </h2>
        <p className="mt-1 text-[11px] text-[var(--trk-text-muted)]">
          Plans onward movement without changing the inbound trip. Trip numbers are minted only when you assign and
          convert to a trip.
        </p>
        {load.active_trip_id ? (
          <p className="mt-2 text-[11px]">
            Inbound trip:{" "}
            <a href={OPS.TRIP_DETAIL(load.active_trip_id)} className="font-mono underline">
              #{load.active_trip_id}
            </a>
          </p>
        ) : null}
        <div className="mt-3 space-y-2 text-[12px]">
          <label className="block">
            <span className="text-[var(--trk-text-muted)]">Pickup terminal (yard)</span>
            <select
              className="mt-0.5 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
              value={terminalId}
              onChange={(e) => setTerminalId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">—</option>
              {terminals.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name || `Terminal ${t.id}`}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[var(--trk-text-muted)]">Planned pickup date/time</span>
            <input
              type="datetime-local"
              className="mt-0.5 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
              value={plannedDate}
              onChange={(e) => setPlannedDate(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-[var(--trk-text-muted)]">Driver</span>
            <select
              className="mt-0.5 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
              value={driverId}
              onChange={(e) => setDriverId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">—</option>
              {drivers.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.first_name} {d.last_name}
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[var(--trk-text-muted)]">Truck</span>
              <select
                className="mt-0.5 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
                value={truckId}
                onChange={(e) => setTruckId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">—</option>
                {trucks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.unit_number || `Truck ${t.id}`}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[var(--trk-text-muted)]">Trailer</span>
              <select
                className="mt-0.5 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1"
                value={trailerId}
                onChange={(e) => setTrailerId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">—</option>
                {trailers.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.unit_number || `Trailer ${t.id}`}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        {error ? <p className="mt-2 text-[11px] text-red-700">{error}</p> : null}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" disabled={busy} onClick={onClose}>
            Close
          </Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => void saveUnassigned()}>
            {busy ? "Saving…" : "Save unassigned"}
          </Button>
          <Button type="button" disabled={busy} onClick={() => void assignAndSave()}>
            {busy ? "Working…" : "Assign driver & save"}
          </Button>
        </div>
      </div>
    </div>
  );
}
