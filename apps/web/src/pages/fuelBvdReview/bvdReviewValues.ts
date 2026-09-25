import type { FuelBvdRow } from "../../api";

export type DraftMap = Record<string, string>;

export function draftKey(rowId: number, field: string) {
  return `${rowId}:${field}`;
}

export function extractedValue(row: FuelBvdRow, field: string): string {
  const v = row[field as keyof FuelBvdRow];
  if (v === null || v === undefined || v === "") return "";
  return String(v);
}

export function persistedReviewed(row: FuelBvdRow, field: string): string | null {
  const c = row.field_corrections?.[field];
  return c?.reviewed_value ?? null;
}

export function reviewedValue(row: FuelBvdRow, field: string, drafts: DraftMap): string {
  const dk = draftKey(row.id, field);
  if (dk in drafts) return drafts[dk];
  const saved = persistedReviewed(row, field);
  if (saved !== null) return saved;
  return extractedValue(row, field);
}

export function isFieldCorrected(row: FuelBvdRow, field: string, drafts: DraftMap): boolean {
  const ext = extractedValue(row, field);
  const rev = reviewedValue(row, field, drafts);
  return ext !== rev;
}

export type FieldSelection = {
  rowId: number;
  field: string;
  label: string;
  row: FuelBvdRow;
};
