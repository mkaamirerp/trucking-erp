import { useRef, useState } from "react";
import { recordStopArrival, recordStopDeparture, type LoadStop } from "@/api";
import { formatCustodyApiError } from "./custodyOperator";
import { showArrive, showDepart } from "./stopExecution";

const btn =
  "rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-text-muted)] hover:bg-[var(--trk-border)] disabled:opacity-45";
const btnPrimary =
  "rounded border border-[var(--trk-heading)]/50 bg-[var(--trk-heading)]/15 px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-heading)] hover:bg-[var(--trk-heading)]/25 disabled:opacity-45";

type Kind = "arrival" | "departure";

export default function StopExecutionActions({
  tripId,
  loadId,
  tripStatus,
  membershipStatus,
  stop,
  onRecorded,
  recordArrival = recordStopArrival,
  recordDeparture = recordStopDeparture,
}: {
  tripId: number;
  loadId: number;
  tripStatus: string;
  membershipStatus: string;
  stop: LoadStop;
  onRecorded: () => Promise<void>;
  recordArrival?: typeof recordStopArrival;
  recordDeparture?: typeof recordStopDeparture;
}) {
  const pendingRef = useRef<Kind | null>(null);
  const [pending, setPending] = useState<Kind | null>(null);
  const [confirming, setConfirming] = useState<Kind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const arrive = showArrive(tripStatus, membershipStatus, stop);
  const depart = showDepart(tripStatus, membershipStatus, stop);

  async function submit(kind: Kind) {
    if (pendingRef.current) return;
    pendingRef.current = kind;
    setPending(kind);
    setError(null);
    try {
      const body = { source: "dispatcher_manual" as const };
      if (kind === "arrival") await recordArrival(tripId, loadId, stop.id, body);
      else await recordDeparture(tripId, loadId, stop.id, body);
      setConfirming(null);
      await onRecorded();
    } catch (err: unknown) {
      setError(formatCustodyApiError(err));
    } finally {
      pendingRef.current = null;
      setPending(null);
    }
  }

  if (!arrive && !depart && !error) return null;

  return (
    <div className="mt-1 flex flex-wrap items-center gap-1" data-testid={`stop-execution-${stop.id}`}>
      {arrive && confirming !== "arrival" ? (
        <button
          type="button"
          className={btn}
          data-testid={`arrive-${stop.id}`}
          disabled={pending != null}
          onClick={() => setConfirming("arrival")}
        >
          Arrive
        </button>
      ) : null}
      {arrive && confirming === "arrival" ? (
        <>
          <span className="text-[9px] text-[var(--trk-text)]">Record arrival for this stop? This does not deliver the Load or complete the Trip.</span>
          <button type="button" className={btn} disabled={pending != null} onClick={() => setConfirming(null)}>
            Go back
          </button>
          <button
            type="button"
            className={btnPrimary}
            data-testid={`arrive-submit-${stop.id}`}
            disabled={pending != null}
            onClick={() => void submit("arrival")}
          >
            Confirm arrival
          </button>
        </>
      ) : null}
      {depart && confirming !== "departure" ? (
        <button
          type="button"
          className={btn}
          data-testid={`depart-${stop.id}`}
          disabled={pending != null}
          onClick={() => setConfirming("departure")}
        >
          Depart
        </button>
      ) : null}
      {depart && confirming === "departure" ? (
        <>
          <span className="text-[9px] text-[var(--trk-text)]">Record departure for this stop? This does not deliver the Load or complete the Trip.</span>
          <button type="button" className={btn} disabled={pending != null} onClick={() => setConfirming(null)}>
            Go back
          </button>
          <button
            type="button"
            className={btnPrimary}
            data-testid={`depart-submit-${stop.id}`}
            disabled={pending != null}
            onClick={() => void submit("departure")}
          >
            Confirm departure
          </button>
        </>
      ) : null}
      {error ? (
        <span className="text-[9px] text-[var(--trk-danger)]" data-testid={`stop-execution-error-${stop.id}`}>
          {error}
        </span>
      ) : null}
    </div>
  );
}
