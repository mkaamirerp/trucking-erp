import type { LoadDocumentParseExtracted } from "../api";

function trimmedNonEmpty(v: string | null | undefined): boolean {
  return typeof v === "string" && v.trim().length > 0;
}

/** Counts non-empty extractors the UI might apply — for honest parse outcome copy only. */
export function countMeaningfulExtractedFields(ex: LoadDocumentParseExtracted): number {
  let n = 0;
  if (trimmedNonEmpty(ex.broker_name_snapshot)) n += 1;
  if (trimmedNonEmpty(ex.broker_contact_name_snapshot)) n += 1;
  if (trimmedNonEmpty(ex.broker_contact_phone_snapshot)) n += 1;
  if (trimmedNonEmpty(ex.broker_contact_email_snapshot)) n += 1;
  if (trimmedNonEmpty(ex.broker_load_reference)) n += 1;
  if (trimmedNonEmpty(ex.broker_mc_number_snapshot)) n += 1;
  if (trimmedNonEmpty(ex.broker_dot_number_snapshot)) n += 1;
  if (trimmedNonEmpty(ex.mode)) n += 1;
  if (trimmedNonEmpty(ex.equipment_type)) n += 1;
  if (trimmedNonEmpty(ex.trailer_type)) n += 1;
  if (trimmedNonEmpty(ex.trailer_size)) n += 1;
  if (trimmedNonEmpty(ex.commodity)) n += 1;
  if (trimmedNonEmpty(ex.temperature_requirement)) n += 1;
  if (ex.estimated_weight != null) n += 1;
  if (ex.rate != null) n += 1;
  if (ex.customer_rate != null) n += 1;
  if (ex.miles != null) n += 1;
  if (trimmedNonEmpty(ex.customs_broker_name)) n += 1;
  if (ex.references?.length) n += 1;
  if (ex.stops?.length) n += 1;
  return n;
}

export type WorkspaceParseOutcomeTone = "success" | "warning" | "neutral";

export type WorkspaceParseOutcome = {
  headline: string;
  tone: WorkspaceParseOutcomeTone;
};

/**
 * Grounded copy from parse-document response only (no backend logic).
 */
export function describeWorkspacePdfParseOutcome(
  extracted: LoadDocumentParseExtracted,
  rawText: string | null | undefined,
  warnings: string[] | null | undefined,
): WorkspaceParseOutcome {
  const w = warnings ?? [];
  const rawLen = (rawText ?? "").trim().length;
  const fieldCount = countMeaningfulExtractedFields(extracted);

  if (fieldCount > 0 && w.length === 0) {
    return {
      headline: "Parsed: extracted fields applied — review before save.",
      tone: "success",
    };
  }
  if (fieldCount > 0 && w.length > 0) {
    return {
      headline: "Parsed: some fields applied — see parse notes below.",
      tone: "warning",
    };
  }
  if (fieldCount === 0 && rawLen > 0) {
    return {
      headline: "Parsed: text found, but no fields matched — see parse notes.",
      tone: "warning",
    };
  }
  return {
    headline: "Parsed: no usable text extracted — see parse notes.",
    tone: "warning",
  };
}
