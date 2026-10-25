import { API_BASE } from "../api";

type Props = {
  objectUrl: string;
  /** When set, show “Open in new tab” for the same PDF bytes (cookie auth on same origin). */
  openInNewTabPath?: string | null;
};

export function loadRateConfirmationPdfDownloadPath(loadId: number): string {
  return `${API_BASE}/loads/${encodeURIComponent(String(loadId))}/rate-confirmation-pdf`;
}

export function draftRateConfirmationPdfDownloadPath(draftId: string): string {
  return `${API_BASE}/load-workspace-drafts/${encodeURIComponent(draftId)}/rate-confirmation-pdf`;
}

export function RateConfirmationPdfPanel({ objectUrl, openInNewTabPath }: Props) {
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)]">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--trk-border)] px-3 py-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
          Rate confirmation PDF
        </span>
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
