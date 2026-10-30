import type { LoadReparseChange } from "@/api";
import Button from "@/components/Button";
import { formatLinehaulDisplay } from "@/loadWorkspace/loadWorkspaceShared";

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

type Props = {
  revision: number;
  filename: string;
  warnings: string[];
  rows: LoadReparseChange[];
  busy: boolean;
  onUseField: (change: LoadReparseChange) => void;
  onClose: () => void;
};

export function ParseReferenceReviewDialog({
  revision,
  filename,
  warnings,
  rows,
  busy,
  onUseField,
  onClose,
}: Props) {
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/55 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="parse-reference-title"
      data-testid="parse-reference-review"
    >
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] shadow-xl">
        <header className="border-b border-[var(--trk-border)] px-4 py-3">
          <h2 id="parse-reference-title" className="text-base font-semibold text-[var(--trk-heading)]">
            Parse PDF — Revised RC {revision}
          </h2>
          <p className="mt-1 text-[11px] text-[var(--trk-text-muted)]">{filename}</p>
          <p className="mt-1 text-[11px] text-[var(--trk-text-muted)]">
            Review extracted values. Use selected fields, then Save load. Nothing is stored until Save.
          </p>
        </header>
        {warnings.length > 0 ? (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-[11px] text-amber-100">
            {warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
        ) : null}
        <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
          {rows.length === 0 ? (
            <p className="text-sm text-[var(--trk-text-muted)]">
              No supported field differences between this PDF and the saved load.
            </p>
          ) : (
            <table className="w-full border-collapse text-[12px]">
              <thead>
                <tr className="border-b border-[var(--trk-border)] text-left text-[var(--trk-text-muted)]">
                  <th className="py-2 pr-2 font-medium">Field</th>
                  <th className="py-2 pr-2 font-medium">Current load</th>
                  <th className="py-2 pr-2 font-medium">Extracted PDF</th>
                  <th className="py-2 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.field} className="border-b border-[var(--trk-border)]/60 align-top">
                    <td className="py-2 pr-2 font-medium text-[var(--trk-text)]">{row.label || row.field}</td>
                    <td className="py-2 pr-2 text-[var(--trk-text-muted)]">
                      {formatCellValue(row.field, row.current_value)}
                    </td>
                    <td className="py-2 pr-2 text-[var(--trk-text)]">
                      {formatCellValue(row.field, row.revised_value)}
                    </td>
                    <td className="py-2">
                      <Button
                        type="button"
                        variant="secondary"
                        className="text-[11px]"
                        disabled={busy || row.editable !== true}
                        data-testid={`parse-use-field-${row.field}`}
                        onClick={() => onUseField(row)}
                      >
                        Use extracted value
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <footer className="flex justify-end gap-2 border-t border-[var(--trk-border)] px-4 py-3">
          <Button type="button" variant="secondary" onClick={onClose} data-testid="parse-reference-close">
            Close
          </Button>
        </footer>
      </div>
    </div>
  );
}
