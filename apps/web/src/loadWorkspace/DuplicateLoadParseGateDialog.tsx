import type { DuplicateLoadCandidate } from "@/api";
import { OPS } from "@/routes";
import { Link, useNavigate } from "react-router-dom";

export type DuplicateLoadParseGateLocationState = {
  reparseRateConfirmationFile?: File;
};

export function formatDuplicateLoadRoute(match: DuplicateLoadCandidate): string {
  const from = (match.pickup || "").trim() || "Pickup unknown";
  const to = (match.delivery || "").trim() || "Delivery unknown";
  return `${from} → ${to}`;
}

type Props = {
  file: File;
  candidates: DuplicateLoadCandidate[];
  busy?: boolean;
  onClose: () => void;
  onReparseExistingLoad: (match: DuplicateLoadCandidate, file: File) => void;
};

export function DuplicateLoadParseGateDialog({
  file,
  candidates,
  busy = false,
  onClose,
  onReparseExistingLoad,
}: Props) {
  const navigate = useNavigate();
  const primary = candidates[0];
  if (!primary) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="duplicate-load-gate-title"
        className="w-full max-w-md rounded-lg border border-amber-500/35 bg-[var(--trk-surface)] p-4 shadow-xl"
      >
        <h2 id="duplicate-load-gate-title" className="text-sm font-semibold text-[var(--trk-heading)]">
          This rate confirmation is already on a load
        </h2>
        <p className="mt-1.5 text-xs text-[var(--trk-text-muted)]">
          Same PDF as an existing load. You cannot create a second load from this file.
        </p>

        <div className="mt-3 rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)]/60 px-3 py-2.5">
          <p className="text-sm font-semibold text-[var(--trk-text)]">
            {primary.broker_name?.trim() || "Broker not recorded"}
          </p>
          <p className="mt-1 text-xs text-[var(--trk-text-muted)]">{formatDuplicateLoadRoute(primary)}</p>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[11px]">
            <dt className="text-[var(--trk-text-muted)]">Load number</dt>
            <dd className="font-mono text-[var(--trk-text)]">{primary.load_number || `#${primary.load_id}`}</dd>
            <dt className="text-[var(--trk-text-muted)]">Broker load #</dt>
            <dd className="font-mono text-[var(--trk-text)]">{primary.broker_load_reference?.trim() || "—"}</dd>
          </dl>
        </div>

        <p className="mt-3 text-xs leading-relaxed text-[var(--trk-text)]">
          Trying to upload a <span className="font-medium">revised</span> rate confirmation for this shipment? Use
          re-parse on the existing load — do not create a new load.
        </p>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
          <button
            type="button"
            disabled={busy}
            className="inline-flex items-center justify-center rounded-md border border-[var(--trk-border)] bg-transparent px-3 py-2 text-sm font-medium text-[var(--trk-text)] hover:bg-[var(--trk-surface-2)] disabled:opacity-50"
            onClick={onClose}
          >
            Not this — close
          </button>
          <Link
            to={OPS.LOAD_DETAIL(primary.load_id)}
            className="inline-flex items-center justify-center rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-3 py-2 text-center text-sm font-semibold text-[var(--trk-text)] hover:border-[var(--trk-border-strong)]"
            onClick={onClose}
          >
            Open load
          </Link>
          <button
            type="button"
            disabled={busy}
            className="inline-flex items-center justify-center rounded-md bg-[var(--trk-heading)] px-3 py-2 text-sm font-semibold text-[var(--trk-bg)] hover:brightness-110 disabled:opacity-50"
            onClick={() => {
              onClose();
              navigate(OPS.LOAD_DETAIL(primary.load_id));
            }}
          >
            Open that load
          </button>
        </div>
      </div>
    </div>
  );
}
