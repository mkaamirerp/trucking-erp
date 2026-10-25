import { useState } from "react";
import {
  changeCurrentEquipment,
  confirmCurrentEquipment,
  getCurrentEquipmentState,
} from "@/api";

/** Explicit physical events; never coupled to saving, starting, or completing a Trip. */
export function ConfirmEquipmentAction({
  driverId, truckId, trailerId, allowConfirm = true,
}: {
  driverId: number | null | undefined;
  truckId: number | null | undefined;
  trailerId: number | null | undefined;
  allowConfirm?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  if (truckId == null) return null;

  const confirm = async () => {
    if (driverId == null || trailerId == null) return;
    if (!window.confirm(
      "Confirm this driver is CURRENTLY with this truck and this trailer is PHYSICALLY HOOKED?\n\n" +
      "This is NOT a future Trip assignment. It will stay recorded after Trip completion."
    )) return;
    setBusy(true);
    setFeedback(null);
    try {
      const existing = await getCurrentEquipmentState(truckId);
      const saved = await confirmCurrentEquipment(truckId, {
        driver_id: driverId,
        trailer_id: trailerId,
        expected_version: existing.version,
      });
      setFeedback(`Current driver/trailer confirmed (v${saved.version}).`);
    } catch (e: unknown) {
      setFeedback(e instanceof Error ? e.message : "Could not confirm equipment.");
    } finally {
      setBusy(false);
    }
  };

  const physicalChange = async (operation: "drop_trailer" | "release_driver") => {
    const label = operation === "drop_trailer" ? "physically DROP the trailer" : "RELEASE the driver from the truck";
    if (!window.confirm(`Confirm you actually ${label}? This does not complete or change any Trip or Load.`)) return;
    setBusy(true);
    setFeedback(null);
    try {
      const current = await getCurrentEquipmentState(truckId);
      if (operation === "drop_trailer" && (trailerId == null || current.trailer_id !== trailerId)) {
        throw new Error("Current trailer differs from this Trip: reopen current equipment before dropping.");
      }
      if (operation === "release_driver" && (driverId == null || current.driver_id !== driverId)) {
        throw new Error("Current driver differs from this Trip: reopen current equipment before release.");
      }
      const saved = await changeCurrentEquipment(truckId, {
        operation, expected_version: current.version,
      });
      setFeedback(
        operation === "drop_trailer"
          ? `Trailer dropped. Truck attachment version ${saved.version}.`
          : `Driver released. Truck attachment version ${saved.version}.`
      );
    } catch (e: unknown) {
      setFeedback(e instanceof Error ? e.message : "Could not update current equipment.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 text-[10px]">
      {allowConfirm && driverId != null && trailerId != null ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void confirm()}
          className="rounded border border-[var(--trk-border-strong)] px-2 py-1 font-semibold text-[var(--trk-text)] disabled:opacity-50"
        >
          {busy ? "Saving…" : "Confirm equipment in use"}
        </button>
      ) : null}
      <button
        type="button"
        disabled={busy}
        onClick={() => void physicalChange("drop_trailer")}
        className="rounded border border-[var(--trk-border)] px-2 py-1 text-[var(--trk-text-muted)] disabled:opacity-50"
      >
        Drop trailer
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => void physicalChange("release_driver")}
        className="rounded border border-[var(--trk-border)] px-2 py-1 text-[var(--trk-text-muted)] disabled:opacity-50"
      >
        Release driver
      </button>
      <span className="text-[var(--trk-text-muted)]">Physical equipment only; Trip assignment unchanged</span>
      {feedback ? <span role="status" className="basis-full text-[var(--trk-text)]">{feedback}</span> : null}
    </div>
  );
}
