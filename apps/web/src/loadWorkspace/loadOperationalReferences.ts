import type { LoadDocumentParseReference } from "@/api";

/** Frontend name for the persisted load-level references collection. */
export type OperationalReference = LoadDocumentParseReference;

export const VISIBLE_INTERNAL_LOAD_NUMBER_LABEL = "TruckERP ID";
export const VISIBLE_BROKER_LOAD_REFERENCE_LABEL = "Load Number";
export const VISIBLE_REFERENCES_SECTION_LABEL = "References";

const KIND_DISPLAY_LABEL: Record<string, string> = {
  po_number: "PO #",
  pickup_number: "Pickup #",
  delivery_number: "Delivery #",
  bol_number: "BOL #",
  appointment_number: "Appointment #",
  shipping_number: "Shipping #",
  receiving_number: "Receiving #",
  freight_bill_number: "Freight Bill #",
  el_number: "EL #",
};

function trimUsefulLabel(label: string | null | undefined): string {
  return typeof label === "string" ? label.trim() : "";
}

/** Copy parser `extracted.references` into workspace state; drop empty items. */
export function workspaceReferencesFromParse(
  refs: LoadDocumentParseReference[] | null | undefined,
): OperationalReference[] {
  if (!Array.isArray(refs)) return [];
  return refs.filter((r) => (r.kind || "").trim().length > 0 && (r.value || "").trim().length > 0);
}

function normalizedReferenceRows(refs: OperationalReference[]): Array<{ kind: string; value: string; label: string }> {
  return refs
    .map((r) => ({
      kind: (r.kind || "").trim(),
      value: (r.value || "").trim(),
      label: (r.label || "").trim(),
    }))
    .filter((r) => r.kind.length > 0 && r.value.length > 0)
    .sort((a, b) => a.kind.localeCompare(b.kind) || a.value.localeCompare(b.value) || a.label.localeCompare(b.label));
}

/** Stable compare for draft vs parse reference collections (kind/value/label preserved). */
export function operationalReferencesFingerprint(refs: OperationalReference[] | null | undefined): string {
  return JSON.stringify(normalizedReferenceRows(refs ?? []));
}

export function draftLoadReferencesDifferFromParsedExtract(
  draftRefs: OperationalReference[] | null | undefined,
  parsedRefs: LoadDocumentParseReference[] | null | undefined,
): boolean {
  const draft = draftRefs ?? [];
  const parsed = workspaceReferencesFromParse(parsedRefs);
  if (draft.length === 0) return false;
  if (parsed.length === 0) return true;
  return operationalReferencesFingerprint(draft) !== operationalReferencesFingerprint(parsed);
}

/** Keep saved reference rows when parse omitted references or operator reviewed them. */
export function shouldPreserveWorkspaceLoadReferences(
  draftRefs: OperationalReference[] | null | undefined,
  parsedRefs: LoadDocumentParseReference[] | null | undefined,
  manuallyEdited: boolean,
): boolean {
  if (manuallyEdited) return true;
  const draft = draftRefs ?? [];
  const parsed = workspaceReferencesFromParse(parsedRefs);
  return draft.length > 0 && parsed.length === 0;
}

export function displayOperationalReferenceLabel(ref: OperationalReference): string {
  const source = trimUsefulLabel(ref.label);
  if (source) return source;
  const mapped = KIND_DISPLAY_LABEL[(ref.kind || "").trim()];
  if (mapped) return mapped;
  return "Reference";
}

/**
 * Compact load-level display: hide a row when that exact value is already shown
 * as a stop `reference_number`. Does not mutate persisted operational_references.
 */
export function compactLoadReferencesForDisplay(
  refs: OperationalReference[],
  stops: Array<{ reference_number?: string | null }>,
): OperationalReference[] {
  const stopVals = new Set(
    stops
      .map((s) => (s.reference_number || "").trim())
      .filter((v) => v.length > 0),
  );
  return refs.filter((r) => !stopVals.has((r.value || "").trim()));
}

export function loadReferencesFromLoad(refs: OperationalReference[] | null | undefined): OperationalReference[] {
  if (!Array.isArray(refs)) return [];
  return refs;
}
