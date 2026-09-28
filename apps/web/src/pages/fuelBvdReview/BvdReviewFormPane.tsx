import { useEffect, useRef } from "react";
import type { FuelBvdRow } from "../../api";
import { getReviewFieldState, isFieldInReviewContract } from "./bvdFieldCapture";
import {
  buildFormSectionsForPage,
  fieldLabel,
  fieldWidthClass,
  type BvdReviewFormSection,
} from "./bvdReviewFormSections";
import { formatReviewLineNumber, type BvdReviewLogicalRow } from "./bvdReviewLines";
import { slotForRef, type BvdFieldRef, type BvdFieldSlot } from "./bvdFieldSlots";
import {
  extractedValue,
  type DraftMap,
  isFieldCorrected,
  reviewedValue,
} from "./bvdReviewValues";

type Props = {
  rows: FuelBvdRow[];
  logicalRows: BvdReviewLogicalRow[];
  currentPage: number;
  drafts: DraftMap;
  readOnly: boolean;
  selected: BvdFieldRef | null;
  activeLineNumber: number | null;
  onSelect: (ref: BvdFieldRef) => void;
  onDraft: (rowId: number, field: string, value: string) => void;
  slots: BvdFieldSlot[];
  /** Results-first review without PDF slot geometry — editable contract fields. */
  resultsFirstNoSlots?: boolean;
};

export default function BvdReviewFormPane({
  rows,
  logicalRows,
  currentPage,
  drafts,
  readOnly,
  selected,
  activeLineNumber,
  onSelect,
  onDraft,
  slots,
  resultsFirstNoSlots = false,
}: Props) {
  const sections: BvdReviewFormSection[] = buildFormSectionsForPage(rows, logicalRows, currentPage);
  const inputRefs = useRef<Map<string, HTMLInputElement>>(new Map());

  useEffect(() => {
    const key = selected?.selectionKey;
    if (!key) return;
    const el = inputRefs.current.get(key);
    el?.scrollIntoView({ block: "nearest", behavior: "instant" as ScrollBehavior });
  }, [selected?.selectionKey, currentPage]);

  const unmappedLines = logicalRows.filter((l) => l.page === currentPage && l.rowType === "UNMAPPED_SOURCE");

  return (
    <div className="bvd-review-form min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-3">
      {sections.map((section) => {
        const lineActive = activeLineNumber === section.reviewLineNumber;
        return (
          <section
            key={`form-line-${section.reviewLineNumber}-${section.title}`}
            className={`bvd-review-form__section${lineActive ? " bvd-review-form__section--active-line" : ""}`}
          >
            <div className="bvd-review-form__line-head">
              <span
                className={`bvd-review-form__line-n${lineActive ? " bvd-review-form__line-n--active" : ""}`}
              >
                {formatReviewLineNumber(section.reviewLineNumber)}
              </span>
              <span className="bvd-review-form__line-title">{section.title}</span>
            </div>
            <div className="bvd-review-form__fields">
              {section.fields.map((ref) => {
                const row = section.row;
                if (!row) return null;
                const fieldState = getReviewFieldState(row, ref.fieldName, slotForRef(slots, ref));
                const showEditable =
                  resultsFirstNoSlots && row
                    ? isFieldInReviewContract(row, ref.fieldName)
                    : fieldState === "captured" || fieldState === "valid_blank";
                const value = reviewedValue(row, ref.fieldName, drafts);
                const corrected = isFieldCorrected(row, ref.fieldName, drafts);
                const captured = extractedValue(row, ref.fieldName);
                const isSel = selected?.selectionKey === ref.selectionKey;
                const label = fieldLabel(ref.fieldName);
                return (
                  <label key={ref.selectionKey} className="bvd-review-field">
                    <span className="bvd-review-field__label">{label}</span>
                    {showEditable ? (
                      <input
                        ref={(el) => {
                          if (el) inputRefs.current.set(ref.selectionKey, el);
                          else inputRefs.current.delete(ref.selectionKey);
                        }}
                        type="text"
                        disabled={readOnly}
                        value={value}
                        placeholder={fieldState === "valid_blank" ? "Blank" : undefined}
                        onFocus={() => onSelect(ref)}
                        onChange={(e) => onDraft(row.id, ref.fieldName, e.target.value)}
                        className={`bvd-review-field__input ${fieldWidthClass(ref.fieldName)}${
                          isSel ? " bvd-review-field__input--selected" : ""
                        }${corrected ? " bvd-review-field__input--corrected" : ""}`}
                        title={corrected ? `Original: ${captured}` : undefined}
                      />
                    ) : (
                      <span className="bvd-review-field__missing" title="Not captured in TruckERP">
                        Not captured
                      </span>
                    )}
                    {corrected ? <span className="bvd-review-field__corrected-tag">Corrected</span> : null}
                  </label>
                );
              })}
            </div>
          </section>
        );
      })}
      {unmappedLines.length > 0 ? (
        <ul className="bvd-review-form__unmapped-lines mt-3 text-xs text-[var(--trk-warning)]">
          {unmappedLines.map((l) => (
            <li key={l.unmappedId ?? l.label}>
              Line {formatReviewLineNumber(l.reviewLineNumber)}: unmapped source — {l.label}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
