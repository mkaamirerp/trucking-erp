import type { FuelBvdRow } from "../../api";
import { BVD_FIELD_LABELS, BVD_HEADER_FIELDS } from "../fuelBvdReviewLabels";
import { fieldRef, fieldsForRowType, type BvdFieldRef } from "./bvdFieldSlots";
import type { BvdReviewLogicalRow } from "./bvdReviewLines";

export type BvdReviewFormSection = {
  reviewLineNumber: number;
  title: string;
  row: FuelBvdRow | null;
  fields: BvdFieldRef[];
};

export function fieldsForLogicalRow(row: FuelBvdRow, logical: BvdReviewLogicalRow): BvdFieldRef[] {
  if (logical.rowType === "HEADER") {
    return BVD_HEADER_FIELDS.map((f) => fieldRef(row, f));
  }
  if (logical.rowType === "UNMAPPED_SOURCE") return [];
  return fieldsForRowType(row.row_type).map((f) => fieldRef(row, f));
}

export function buildFormSectionsForPage(
  rows: FuelBvdRow[],
  logicalRows: BvdReviewLogicalRow[],
  page: number,
): BvdReviewFormSection[] {
  const rowById = new Map(rows.map((r) => [r.id, r]));
  return logicalRows
    .filter((l) => l.page === page && l.rowType !== "UNMAPPED_SOURCE")
    .sort((a, b) => a.reviewLineNumber - b.reviewLineNumber)
    .map((logical) => {
      const row = rowById.get(logical.fuelBvdId) ?? null;
      const fields = row ? fieldsForLogicalRow(row, logical) : [];
      return {
        reviewLineNumber: logical.reviewLineNumber,
        title: logical.label,
        row,
        fields,
      };
    })
    .filter((s) => s.fields.length > 0);
}

export function fieldLabel(fieldName: string): string {
  return BVD_FIELD_LABELS[fieldName] ?? fieldName;
}

export function fieldWidthClass(fieldName: string): string {
  const narrow = new Set([
    "unit_number",
    "prov_st",
    "cur",
    "qty",
    "pst",
    "gst",
    "hst",
    "qst",
    "disc_rate",
    "site_number",
    "prod",
    "legend_code",
  ]);
  const wide = new Set(["client_address", "site_name", "driver_name", "client_name"]);
  if (narrow.has(fieldName)) return "bvd-review-field__input--narrow";
  if (wide.has(fieldName)) return "bvd-review-field__input--wide";
  return "bvd-review-field__input--medium";
}
