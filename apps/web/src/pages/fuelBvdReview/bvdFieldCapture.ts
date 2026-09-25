import type { FuelBvdRow } from "../../api";
import type { BvdFieldSlot } from "./bvdFieldSlots";
import { fieldsForRowType } from "./bvdFieldSlots";
import { extractedValue } from "./bvdReviewValues";

export type ReviewFieldState = "captured" | "valid_blank" | "not_captured" | "unmapped";

export function isFieldInReviewContract(row: FuelBvdRow, fieldName: string): boolean {
  return fieldsForRowType(row.row_type).includes(fieldName);
}

/**
 * Review overlay state — separate from empty string content.
 * - captured: mapped slot + non-empty extracted/reviewed value
 * - valid_blank: mapped slot + intentional empty source (e.g. blank client_email)
 * - not_captured: contract field but no reliable slot / mapping
 * - unmapped: outside known review contract (should not render as captured)
 */
export function getReviewFieldState(
  row: FuelBvdRow,
  fieldName: string,
  slot: BvdFieldSlot | undefined,
): ReviewFieldState {
  if (!isFieldInReviewContract(row, fieldName)) return "unmapped";
  if (!slot || slot.ambiguous) return "not_captured";

  const ext = extractedValue(row, fieldName);
  const hasCorrection = Boolean(row.field_corrections?.[fieldName]);
  if (ext === "" && !hasCorrection) return "valid_blank";
  return "captured";
}
