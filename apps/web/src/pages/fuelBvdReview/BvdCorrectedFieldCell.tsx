import { useEffect, useRef, useState } from "react";
import type { FuelBvdRow } from "../../api";
import { fieldsForRowType } from "./bvdFieldSlots";
import { bvdParserMoneyBaseline, bvdReviewFieldDisplay, isBvdProviderMoneyField } from "./bvdParsedDisplay";
import {
  extractedValue,
  isFieldCorrected,
  reviewedValue,
  type DraftMap,
} from "./bvdReviewValues";

type Props = {
  row: FuelBvdRow;
  field: string;
  drafts?: DraftMap;
  presentation: "processing-review" | "full-stored-detail";
  readOnly?: boolean;
  /** Persist unsaved edits locally until Save review / Process (processing workspace). */
  onFieldDraft?: (rowId: number, field: string, value: string) => void;
  onInlineCommit?: (rowId: number, field: string, value: string) => void | Promise<void>;
};

export default function BvdCorrectedFieldCell({
  row,
  field,
  drafts = {},
  presentation,
  readOnly = false,
  onFieldDraft,
  onInlineCommit,
}: Props) {
  const extracted = extractedValue(row, field);
  const effective = reviewedValue(row, field, drafts);
  const corrected = isFieldCorrected(row, field, drafts);
  const display = bvdReviewFieldDisplay(row, field, drafts);
  const editable =
    presentation === "processing-review" &&
    !readOnly &&
    Boolean(onFieldDraft || onInlineCommit) &&
    fieldsForRowType(row.row_type).includes(field);

  const [editing, setEditing] = useState(false);
  const [local, setLocal] = useState(display === "—" ? "" : display);
  const parserBaseline = bvdParserMoneyBaseline(field, extracted);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) {
      setLocal(display === "—" ? "" : display);
    }
  }, [display, editing]);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const commit = async () => {
    const next = local.trim();
    setEditing(false);
    if (onFieldDraft) {
      onFieldDraft(row.id, field, next);
      return;
    }
    const baseline = isBvdProviderMoneyField(field) ? parserBaseline : extracted || "";
    if (next === baseline && !corrected) {
      return;
    }
    const effectiveRaw = effective || extracted;
    if (next === effectiveRaw || (isBvdProviderMoneyField(field) && next === bvdReviewFieldDisplay(row, field, drafts))) {
      return;
    }
    await onInlineCommit?.(row.id, field, next);
  };

  if (editable && editing) {
    return (
      <input
        ref={inputRef}
        className="bvd-inline-edit-input w-full min-w-[3rem] rounded border border-[var(--trk-accent)] bg-[var(--trk-surface)] px-1 py-0.5 text-xs"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            void commit();
          }
          if (e.key === "Escape") {
            setEditing(false);
            setLocal(display === "—" ? "" : display);
          }
        }}
        aria-label={`Edit ${field}`}
      />
    );
  }

  if (!corrected) {
    if (editable) {
      return (
        <button
          type="button"
          className="bvd-inline-edit-trigger w-full text-left hover:underline"
          onClick={() => setEditing(true)}
          title="Click to edit"
        >
          {display}
        </button>
      );
    }
    return <>{display}</>;
  }

  if (presentation === "full-stored-detail") {
    return (
      <div className="bvd-corrected-cell bvd-corrected-cell--detail">
        <span className="bvd-corrected-cell__effective">{display}</span>
        {row.field_corrections?.[field] ? (
          <>
            <span className="bvd-corrected-cell__badge">Corrected during review</span>
            <span className="bvd-corrected-cell__extracted">Extracted: {extracted || "—"}</span>
          </>
        ) : null}
      </div>
    );
  }

  const cellBody = (
    <>
      {display}
      <span className="bvd-corrected-cell__mark" aria-label="Corrected"> *</span>
    </>
  );

  if (editable) {
    return (
      <button
        type="button"
        className="bvd-corrected-cell bvd-corrected-cell--inline bvd-inline-edit-trigger w-full text-left"
        title={`Extracted: ${extracted || "—"}\nReviewed: ${effective}`}
        onClick={() => setEditing(true)}
      >
        {cellBody}
      </button>
    );
  }

  return (
    <span
      className="bvd-corrected-cell bvd-corrected-cell--inline"
      title={`Extracted: ${extracted || "—"}\nReviewed: ${effective}`}
    >
      {cellBody}
    </span>
  );
}
