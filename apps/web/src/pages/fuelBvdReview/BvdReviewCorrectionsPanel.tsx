import { useMemo, useState } from "react";
import type { FuelBvdRow } from "../../api";
import BvdReviewFormPane from "./BvdReviewFormPane";
import { buildReviewLogicalRows } from "./bvdReviewLines";
import type { BvdFieldRef } from "./bvdFieldSlots";
import type { DraftMap } from "./bvdReviewValues";
import "./bvd-review-form.css";

type Props = {
  rows: FuelBvdRow[];
  drafts: DraftMap;
  readOnly: boolean;
  onDraft: (rowId: number, field: string, value: string) => void;
};

export default function BvdReviewCorrectionsPanel({ rows, drafts, readOnly, onDraft }: Props) {
  const logicalRows = useMemo(() => buildReviewLogicalRows(rows), [rows]);
  const pages = useMemo(() => {
    const set = new Set(logicalRows.map((l) => l.page));
    return [...set].sort((a, b) => a - b);
  }, [logicalRows]);
  const [currentPage, setCurrentPage] = useState(pages[0] ?? 1);
  const [selected, setSelected] = useState<BvdFieldRef | null>(null);

  if (logicalRows.length === 0) {
    return null;
  }

  return (
    <section
      className="bvd-corrections-panel mx-3 mb-3 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)]"
      data-testid="bvd-review-corrections-panel"
      aria-label="Review corrections"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--trk-border)] px-3 py-2">
        <div>
          <h2 className="text-sm font-semibold text-[var(--trk-text)]">Review corrections</h2>
          <p className="text-xs text-[var(--trk-text-muted)]">
            Edit reviewed values before Process. Original extracted source stays immutable; Save review persists
            corrections.
          </p>
        </div>
        {pages.length > 1 ? (
          <div className="flex gap-1">
            {pages.map((p) => (
              <button
                key={p}
                type="button"
                className={`rounded px-2 py-0.5 text-xs ${
                  p === currentPage
                    ? "bg-[var(--trk-accent)] text-[var(--trk-btn-text)]"
                    : "border border-[var(--trk-border)] text-[var(--trk-text-muted)]"
                }`}
                onClick={() => setCurrentPage(p)}
              >
                Page {p}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <div className="max-h-[min(42vh,28rem)] min-h-[12rem]">
        <BvdReviewFormPane
          rows={rows}
          logicalRows={logicalRows}
          currentPage={currentPage}
          drafts={drafts}
          readOnly={readOnly}
          selected={selected}
          activeLineNumber={null}
          onSelect={setSelected}
          onDraft={onDraft}
          slots={[]}
          resultsFirstNoSlots
        />
      </div>
    </section>
  );
}
