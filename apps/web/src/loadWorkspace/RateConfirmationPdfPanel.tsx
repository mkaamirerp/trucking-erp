import { API_BASE } from "../api";
import {
  parseConfidenceAppliedChipClasses,
  parseConfidenceRcPanelClasses,
  parseConfidenceTierLabel,
  type ParseConfidenceTier,
} from "@/loadWorkspace/parseFieldConfidenceUi";

type Props = {
  objectUrl: string;
  /** When set, show “Open in new tab” for the same PDF bytes (cookie auth on same origin). */
  openInNewTabPath?: string | null;
  /** Overall parse confidence — drives RC panel accent for dispatch review. */
  parseConfidenceTier?: ParseConfidenceTier | null;
};

export function loadRateConfirmationPdfDownloadPath(loadId: number): string {
  return `${API_BASE}/loads/${encodeURIComponent(String(loadId))}/rate-confirmation-pdf`;
}

export function draftRateConfirmationPdfDownloadPath(draftId: string): string {
  return `${API_BASE}/load-workspace-drafts/${encodeURIComponent(draftId)}/rate-confirmation-pdf`;
}

export function RateConfirmationPdfPanel({
  objectUrl,
  openInNewTabPath,
  parseConfidenceTier = "medium",
}: Props) {
  const tier = parseConfidenceTier ?? "medium";
  const rc = parseConfidenceRcPanelClasses(tier);
  return (
    <div
      className={`overflow-hidden rounded-lg border bg-[var(--trk-surface)] ${rc.border}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--trk-border)] px-3 py-2.5">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span
            className={`shrink-0 rounded-md px-2.5 py-1 text-sm font-bold tracking-wide ${rc.badge}`}
            title="Rate confirmation document"
          >
            RC
          </span>
          <span className={`text-xs font-bold uppercase tracking-wide ${rc.title}`}>
            Rate confirmation PDF
          </span>
          <span
            className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${parseConfidenceAppliedChipClasses(tier)}`}
          >
            {parseConfidenceTierLabel(tier)}
          </span>
        </div>
        {openInNewTabPath ? (
          <a
            href={openInNewTabPath}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 text-[10px] font-medium text-sky-600 underline-offset-2 hover:underline dark:text-sky-400"
          >
            Open in new tab
          </a>
        ) : null}
      </div>
      <iframe
        data-testid="rate-confirmation-pdf-viewer"
        title="Rate confirmation PDF"
        src={objectUrl}
        className="h-[min(42vh,320px)] w-full bg-white"
      />
    </div>
  );
}
