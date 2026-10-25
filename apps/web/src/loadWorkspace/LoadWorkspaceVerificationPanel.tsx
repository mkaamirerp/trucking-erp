import { type MutableRefObject, type ReactNode, type RefObject } from "react";
import Button from "@/components/Button";
import { RateConfirmationPdfPanel } from "@/loadWorkspace/RateConfirmationPdfPanel";
import { wsSectionTitle } from "@/loadWorkspace/loadWorkspaceShared";

export type VerificationLeftTab = "text" | "pdf";

export function LoadWorkspaceVerificationPanel({
  docLines,
  docScrollRef,
  docLineRefs,
  activeDocLine,
  extractedEmptyMessage,
  pdfObjectUrl,
  pdfOpenInNewTabPath,
  canUploadParse,
  parseBusy,
  parseElapsedSec,
  onUploadParseClick,
  intakeEmailSlot,
  activeTab,
  onTabChange,
}: {
  docLines: string[];
  docScrollRef: RefObject<HTMLDivElement>;
  docLineRefs: MutableRefObject<Map<number, HTMLDivElement | null>>;
  activeDocLine: number | null;
  extractedEmptyMessage: string;
  pdfObjectUrl: string | null;
  pdfOpenInNewTabPath: string | null;
  canUploadParse: boolean;
  parseBusy: boolean;
  parseElapsedSec: number;
  onUploadParseClick: () => void;
  intakeEmailSlot?: ReactNode;
  activeTab: VerificationLeftTab;
  onTabChange: (tab: VerificationLeftTab) => void;
}) {
  const tabBtn = (id: VerificationLeftTab, label: string) => (
    <button
      type="button"
      data-testid={`verification-tab-${id}`}
      className={`rounded px-2.5 py-1 text-[11px] font-semibold ${
        activeTab === id
          ? "bg-[var(--trk-heading)] text-[var(--trk-bg)]"
          : "text-[var(--trk-text-muted)] hover:text-[var(--trk-text)]"
      }`}
      onClick={() => onTabChange(id)}
    >
      {label}
    </button>
  );

  return (
    <div
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)]"
      data-testid="load-workspace-verification-panel"
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--trk-border)] px-3 py-2">
        <div className="flex gap-1">
          {tabBtn("text", "Extracted text")}
          {tabBtn("pdf", "PDF")}
        </div>
        {canUploadParse ? (
          <Button
            variant="secondary"
            type="button"
            className="!px-2 !py-1 !text-[10px]"
            disabled={parseBusy}
            onClick={onUploadParseClick}
          >
            {parseBusy
              ? parseElapsedSec > 0
                ? `Parsing… ${parseElapsedSec}s`
                : "Parsing…"
              : "Upload & parse"}
          </Button>
        ) : null}
      </div>
      {intakeEmailSlot ? (
        <div className="shrink-0 border-b border-[var(--trk-border)]">{intakeEmailSlot}</div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === "text" ? (
          <div className="flex h-full min-h-0 flex-col">
            <div className="shrink-0 border-b border-[var(--trk-border)] px-3 py-2">
              <span className={wsSectionTitle}>Extracted text</span>
              <p className="mt-1 text-[11px] leading-snug text-[var(--trk-text-muted)]">
                Focus a field on the right to jump to matching lines here.
              </p>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3" data-testid="verification-extracted-text">
              {docLines.length ? (
                <div
                  ref={docScrollRef}
                  className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] p-2 font-mono text-[11px] leading-snug text-[var(--trk-text)]"
                >
                  {docLines.map((line, i) => (
                    <div
                      key={i}
                      data-testid={activeDocLine === i ? "verification-line-active" : undefined}
                      ref={(el) => {
                        docLineRefs.current.set(i, el);
                      }}
                      className="whitespace-pre-wrap break-words rounded px-1 py-0.5"
                      style={activeDocLine === i ? { background: "rgba(245,166,35,0.2)" } : undefined}
                    >
                      {line || " "}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-md border border-dashed border-[var(--trk-border)] bg-[var(--trk-bg)]/50 px-3 py-8 text-center text-xs text-[var(--trk-text-muted)]">
                  {extractedEmptyMessage}
                </p>
              )}
            </div>
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col p-2">
            {pdfObjectUrl ? (
              <RateConfirmationPdfPanel
                objectUrl={pdfObjectUrl}
                openInNewTabPath={pdfOpenInNewTabPath}
                className="h-full min-h-0 flex-1"
                iframeClassName="min-h-0 flex-1 w-full bg-white"
              />
            ) : (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-[var(--trk-border)] bg-[var(--trk-bg)]/40 px-4 py-10 text-center">
                <p className="text-sm font-medium text-[var(--trk-text)]">No rate confirmation PDF</p>
                <p className="max-w-xs text-xs text-[var(--trk-text-muted)]">
                  Upload a rate confirmation to view the PDF here and verify fields on the right.
                </p>
                {canUploadParse ? (
                  <Button variant="secondary" type="button" disabled={parseBusy} onClick={onUploadParseClick}>
                    Upload &amp; parse PDF
                  </Button>
                ) : null}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
