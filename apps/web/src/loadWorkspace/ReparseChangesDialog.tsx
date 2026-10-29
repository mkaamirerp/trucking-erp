import { useEffect, useState } from "react";
import type { LoadReparseChange } from "@/api";
import Button from "@/components/Button";
import { formatLinehaulDisplay } from "@/loadWorkspace/loadWorkspaceShared";
import clsx from "clsx";

function formatCellValue(field: string, value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  if (field === "rate" || field === "customer_rate") {
    const money = formatLinehaulDisplay(text.replace(/^\$/, "").trim());
    if (money) return money;
  }
  return text;
}

function isMoneyField(field: string): boolean {
  return field === "rate" || field === "customer_rate";
}

type Props = {
  changes: LoadReparseChange[];
  summary?: string;
  reasons?: string[];
  verdict?: string;
  acknowledgementRequired?: boolean;
  acknowledgementReason?: string;
  onAcknowledgementReason?: (value: string) => void;
  otherLoadId?: number | null;
  onOpenOtherLoad?: () => void;
  busy: boolean;
  onApplyField: (change: LoadReparseChange) => void;
  onUndoField: (change: LoadReparseChange) => void;
  onCloseWrongFile: () => void;
  onDoneBackToLoad: () => void;
  onCancelReparse: () => void;
};

export function ReparseChangesDialog({
  changes,
  summary = "",
  reasons = [],
  verdict = "",
  acknowledgementRequired = false,
  acknowledgementReason = "",
  onAcknowledgementReason,
  otherLoadId = null,
  onOpenOtherLoad,
  busy,
  onApplyField,
  onUndoField,
  onCloseWrongFile,
  onDoneBackToLoad,
  onCancelReparse,
}: Props) {
  const strongMatch = !acknowledgementRequired && verdict === "strong";
  const diffCount = changes.length;
  const showWarningPanel =
    acknowledgementRequired || reasons.length > 0 || Boolean(summary.trim());

  /** Warning flow: table visible immediately; row actions unlock after Continue anyway. */
  const [warningContinued, setWarningContinued] = useState(false);
  const [appliedFields, setAppliedFields] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setWarningContinued(false);
    setAppliedFields(new Set());
  }, [acknowledgementRequired, summary, verdict, diffCount, changes]);

  const valuesUnlocked = !acknowledgementRequired || warningContinued;

  const warningLead =
    reasons.find((r) => /check this pdf|needs confirmation|historical|cannot confirm/i.test(r)) ||
    (acknowledgementRequired ? "Check this PDF before you continue." : "");

  const warningDetail = summary.trim();
  const extraReasons = reasons.filter(
    (r) => r.trim() && r.trim() !== warningDetail && r !== warningLead,
  );

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/55 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="reparse-dialog-title"
    >
      <div
        className={clsx(
          "flex max-h-[min(88vh,720px)] w-full max-w-2xl flex-col overflow-hidden rounded-lg border shadow-xl",
          strongMatch
            ? "border-emerald-500/35 bg-[var(--trk-surface)]"
            : "border-amber-500/30 bg-[var(--trk-surface)]",
        )}
      >
        <div
          className={clsx(
            "shrink-0 border-b px-4 py-3",
            strongMatch
              ? "border-emerald-500/25 bg-emerald-950/20"
              : "border-[var(--trk-border)] bg-[var(--trk-bg)]/40",
          )}
        >
          <h2 id="reparse-dialog-title" className="text-base font-semibold text-[var(--trk-heading)]">
            Revised rate confirmation
          </h2>
          <p className="mt-0.5 text-sm text-[var(--trk-text-muted)]">
            {diffCount === 0
              ? "The new PDF matches this load."
              : `${diffCount} difference${diffCount === 1 ? "" : "s"} found in the new PDF`}
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {showWarningPanel ? (
            <div className="mb-3 rounded-lg border border-amber-500/45 bg-amber-950/35 px-3 py-3">
              {warningLead ? (
                <p className="text-sm font-semibold text-amber-100">{warningLead}</p>
              ) : (
                <p className="text-sm font-semibold text-amber-100">Check this PDF before you continue.</p>
              )}
              {warningDetail ? (
                <p className="mt-2 text-sm leading-relaxed text-amber-100/90">{warningDetail}</p>
              ) : null}
              {extraReasons.length > 0 ? (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-100/85">
                  {extraReasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}
              {acknowledgementRequired && !warningContinued ? (
                <p className="mt-2 text-xs text-amber-100/80">
                  Review the table below, then choose Continue anyway to enable Use new value on rows you want on
                  the form.
                </p>
              ) : null}
            </div>
          ) : null}

          {diffCount > 0 ? (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--trk-border)] text-xs uppercase tracking-wide text-[var(--trk-text-muted)]">
                  <th className="py-2 pr-2 font-medium">Field</th>
                  <th className="py-2 pr-2 font-medium">On this load</th>
                  <th className="py-2 pr-2 font-medium">New PDF</th>
                  <th className="py-2 text-right font-medium" />
                </tr>
              </thead>
              <tbody>
                {changes.map((change) => {
                  const canApply = change.editable === true && valuesUnlocked;
                  const applied = appliedFields.has(change.field);
                  return (
                    <tr
                      key={change.field}
                      className={clsx(
                        "border-b border-[var(--trk-border)]/70",
                        applied && "bg-emerald-950/25",
                      )}
                    >
                      <td className="py-2.5 pr-2 align-top font-medium text-[var(--trk-text)]">
                        {change.label}
                        {change.explanation ? (
                          <div className="mt-0.5 font-normal text-xs text-[var(--trk-text-muted)]">
                            {change.explanation}
                          </div>
                        ) : null}
                        {isMoneyField(change.field) && change.editable === true ? (
                          <span className="mt-1 inline-block rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-200/95">
                            Money · check the PDF
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2.5 pr-2 align-top font-mono text-[var(--trk-text)]">
                        {formatCellValue(change.field, change.current_value)}
                      </td>
                      <td className="py-2.5 pr-2 align-top font-mono font-semibold text-[var(--trk-heading)]">
                        {formatCellValue(change.field, change.revised_value)}
                      </td>
                      <td className="py-2.5 align-top text-right">
                        {change.editable === true ? (
                          applied ? (
                            <div className="flex flex-col items-end gap-0.5">
                              <span className="text-xs font-semibold text-emerald-300">✓ On the form</span>
                              <button
                                type="button"
                                className="text-[11px] font-medium text-emerald-200/95 underline underline-offset-2 hover:text-emerald-100 disabled:opacity-50"
                                disabled={busy}
                                onClick={() => {
                                  onUndoField(change);
                                  setAppliedFields((prev) => {
                                    const next = new Set(prev);
                                    next.delete(change.field);
                                    return next;
                                  });
                                }}
                              >
                                Undo
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className={clsx(
                                "rounded-md border px-2.5 py-1 text-xs font-semibold",
                                canApply
                                  ? "border-[var(--trk-heading)]/40 bg-[var(--trk-bg)] text-[var(--trk-heading)] hover:bg-[var(--trk-surface-2)]"
                                  : "cursor-not-allowed border-[var(--trk-border)] bg-[var(--trk-bg)]/60 text-[var(--trk-text-muted)] opacity-70",
                              )}
                              disabled={busy || !canApply}
                              title={
                                !valuesUnlocked
                                  ? "Choose Continue anyway below before applying values from this PDF."
                                  : undefined
                              }
                              onClick={() => {
                                onApplyField(change);
                                setAppliedFields((prev) => new Set(prev).add(change.field));
                              }}
                            >
                              Use new value
                            </button>
                          )
                        ) : (
                          <span className="text-xs text-[var(--trk-text-muted)]">Review only</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-[var(--trk-text-muted)]">
              Nothing to apply on the form. You can still save if you need to keep this PDF on the load.
            </p>
          )}

          {acknowledgementRequired ? (
            <label className="mt-4 block text-sm text-[var(--trk-text)]">
              <span className="font-medium text-amber-200/95">Why are you saving this revised PDF? (required)</span>
              <textarea
                className="mt-1.5 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2.5 py-2 text-sm text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)]"
                rows={2}
                placeholder="Example: broker sent a corrected rate confirmation by email"
                value={acknowledgementReason}
                disabled={busy}
                onChange={(event) => onAcknowledgementReason?.(event.target.value)}
              />
              <span className="mt-1 block text-xs text-[var(--trk-text-muted)]">
                This is recorded on the load with the PDF.
              </span>
            </label>
          ) : null}

          <p className="mt-3 text-xs text-[var(--trk-text-muted)]">
            Use new value updates the form only. Nothing is stored until you click Save load on the load page.
          </p>
        </div>

        <div className="shrink-0 border-t border-[var(--trk-border)] bg-[var(--trk-bg)]/50 px-4 py-3">
          {acknowledgementRequired ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              {warningContinued ? (
                <button
                  type="button"
                  className="rounded-md border border-[var(--trk-border-strong)] bg-transparent px-3 py-2 text-sm font-medium text-[var(--trk-text)] underline-offset-2 hover:bg-[var(--trk-surface-2)] hover:underline disabled:opacity-50"
                  disabled={busy}
                  onClick={onDoneBackToLoad}
                >
                  Done, back to the load
                </button>
              ) : (
                <button
                  type="button"
                  className="rounded-md border border-[var(--trk-border-strong)] bg-transparent px-3 py-2 text-sm font-medium text-[var(--trk-text)] underline-offset-2 hover:bg-[var(--trk-surface-2)] hover:underline disabled:opacity-50"
                  disabled={busy}
                  onClick={() => setWarningContinued(true)}
                >
                  Continue anyway
                </button>
              )}
              <div className="flex flex-wrap items-center justify-end gap-2">
                {otherLoadId != null && onOpenOtherLoad ? (
                  <Button
                    type="button"
                    variant="secondary"
                    className="border border-[var(--trk-border)] bg-transparent text-[var(--trk-text)] hover:bg-[var(--trk-surface-2)]"
                    disabled={busy}
                    onClick={onOpenOtherLoad}
                  >
                    Open the other load
                  </Button>
                ) : null}
                <button
                  type="button"
                  className="inline-flex items-center justify-center rounded-md bg-[var(--trk-heading)] px-3 py-2 text-sm font-semibold text-[var(--trk-bg)] shadow-sm hover:brightness-110 disabled:opacity-50"
                  disabled={busy}
                  onClick={onCloseWrongFile}
                >
                  Close, wrong file
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                variant="secondary"
                className="border border-[var(--trk-border)] bg-transparent text-[var(--trk-text)] hover:bg-[var(--trk-surface-2)]"
                disabled={busy}
                onClick={onCancelReparse}
              >
                Cancel re-parse
              </Button>
              <Button
                type="button"
                className={clsx(
                  strongMatch
                    ? "border border-emerald-500/40 bg-emerald-700 text-white hover:bg-emerald-600"
                    : "bg-[var(--trk-btn-primary)] text-[var(--trk-btn-text)] hover:brightness-110",
                )}
                disabled={busy}
                onClick={onDoneBackToLoad}
              >
                Done, back to the load
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
