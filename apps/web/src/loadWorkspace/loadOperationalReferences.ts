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
