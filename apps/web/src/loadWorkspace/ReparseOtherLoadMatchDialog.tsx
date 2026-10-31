import type { Driver, DuplicateLoadCandidate } from "@/api";

function formatPlace(value: string | null | undefined): string {
  const t = (value ?? "").trim();
  return t || "Not set";
}

function driverLine(candidate: DuplicateLoadCandidate, drivers: Driver[]): string {
  if (candidate.driver_id == null) return "No driver assigned";
  const match = drivers.find((d) => d.id === candidate.driver_id);
  if (match) {
    const name = `${match.first_name ?? ""} ${match.last_name ?? ""}`.trim();
    if (name) return name;
  }
  return "Driver assigned";
}

function statusLine(candidate: DuplicateLoadCandidate): string {
  const load = (candidate.load_status ?? "").trim() || "—";
  const trip = (candidate.trip_status ?? "").trim();
  if (trip) return `${load} (trip: ${trip})`;
  return load;
}

type Props = {
  candidates: DuplicateLoadCandidate[];
  drivers: Driver[];
  onClose: () => void;
};

export function ReparseOtherLoadMatchDialog({ candidates, drivers, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="reparse-other-load-title"
        className="w-full max-w-md rounded-lg border border-amber-500/35 bg-[var(--trk-surface)] p-4 shadow-xl"
      >
        <h2 id="reparse-other-load-title" className="text-sm font-semibold text-[var(--trk-heading)]">
          This PDF matches a different load
        </h2>
        <p className="mt-1.5 text-xs text-[var(--trk-text-muted)]">Nothing was changed.</p>

        <div className="mt-3 max-h-[50vh] space-y-2 overflow-y-auto">
          {candidates.map((candidate) => (
            <div
              key={candidate.load_id}
              className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)]/60 px-3 py-2.5"
            >
              <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-[11px]">
                <dt className="text-[var(--trk-text-muted)]">Load number</dt>
                <dd className="font-mono text-[var(--trk-text)]">
                  {candidate.load_number || `#${candidate.load_id}`}
                </dd>
                <dt className="text-[var(--trk-text-muted)]">Pickup</dt>
                <dd className="text-[var(--trk-text)]">{formatPlace(candidate.pickup)}</dd>
                <dt className="text-[var(--trk-text-muted)]">Delivery</dt>
                <dd className="text-[var(--trk-text)]">{formatPlace(candidate.delivery)}</dd>
                <dt className="text-[var(--trk-text-muted)]">Driver</dt>
                <dd className="text-[var(--trk-text)]">{driverLine(candidate, drivers)}</dd>
                <dt className="text-[var(--trk-text-muted)]">Status</dt>
                <dd className="text-[var(--trk-text)]">{statusLine(candidate)}</dd>
              </dl>
            </div>
          ))}
        </div>

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-md bg-[var(--trk-heading)] px-3 py-2 text-sm font-semibold text-[var(--trk-bg)] hover:brightness-110"
            onClick={onClose}
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
}
