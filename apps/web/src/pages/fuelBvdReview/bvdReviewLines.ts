import type { FuelBvdRow } from "../../api";
import { BVD_FIELD_LABELS, BVD_HEADER_FIELDS } from "../fuelBvdReviewLabels";
import type { BvdFieldSlot } from "./bvdFieldSlots";
import type { BvdUnmappedSourceField } from "./bvdUnmappedSource";

export type BvdReviewLogicalRow = {
  /** Invoice-wide 1-based line number (shared left/right). */
  reviewLineNumber: number;
  fuelBvdId: number;
  rowType: string;
  page: number;
  /** Header: single field; transaction: undefined (whole row). */
  headerField?: string;
  label: string;
  unmappedId?: string;
  /** Vertical sort key within page (PDF geometry). */
  sortTop?: number;
};

const TYPE_ORDER = ["HEADER", "TRANSACTION", "TRANSACTION_SUBTOTAL", "PAGE1_SUMMARY", "GRAND_TOTAL", "LEGEND"];

function rowSort(a: FuelBvdRow, b: FuelBvdRow): number {
  const pa = a.source_page ?? 1;
  const pb = b.source_page ?? 1;
  if (pa !== pb) return pa - pb;
  const ta = TYPE_ORDER.indexOf(a.row_type);
  const tb = TYPE_ORDER.indexOf(b.row_type);
  if (ta !== tb) return ta - tb;
  return (a.source_row_number ?? 0) - (b.source_row_number ?? 0);
}

/** One shared numbering model for the whole import (not per-page). */
export function buildReviewLogicalRows(rows: FuelBvdRow[]): BvdReviewLogicalRow[] {
  const sorted = [...rows].sort(rowSort);
  const out: BvdReviewLogicalRow[] = [];
  let n = 0;

  const header = sorted.find((r) => r.row_type === "HEADER");
  if (header) {
    for (const field of BVD_HEADER_FIELDS) {
      n += 1;
      out.push({
        reviewLineNumber: n,
        fuelBvdId: header.id,
        rowType: "HEADER",
        page: header.source_page ?? 1,
        headerField: field,
        label: BVD_FIELD_LABELS[field] ?? field,
      });
    }
  }

  for (const row of sorted) {
    if (row.row_type === "TRANSACTION") {
      n += 1;
      const auth = row.auth_code ? ` ${row.auth_code}` : "";
      out.push({
        reviewLineNumber: n,
        fuelBvdId: row.id,
        rowType: "TRANSACTION",
        page: row.source_page ?? 1,
        label: `Transaction${auth}`,
      });
    } else if (row.row_type === "TRANSACTION_SUBTOTAL" || row.row_type === "PAGE1_SUMMARY") {
      n += 1;
      out.push({
        reviewLineNumber: n,
        fuelBvdId: row.id,
        rowType: row.row_type,
        page: row.source_page ?? 1,
        label: row.row_label ?? "Subtotal",
      });
    } else if (row.row_type === "GRAND_TOTAL") {
      n += 1;
      out.push({
        reviewLineNumber: n,
        fuelBvdId: row.id,
        rowType: "GRAND_TOTAL",
        page: row.source_page ?? 1,
        label: `Grand Total ${row.product ?? ""}`.trim(),
      });
    } else if (row.row_type === "LEGEND") {
      n += 1;
      out.push({
        reviewLineNumber: n,
        fuelBvdId: row.id,
        rowType: "LEGEND",
        page: row.source_page ?? 1,
        label: `Legend ${row.legend_code ?? ""}`.trim(),
      });
    }
  }

  return out;
}

type LogicalDraft = Omit<BvdReviewLogicalRow, "reviewLineNumber">;

function estimateSortTop(line: LogicalDraft, slots: BvdFieldSlot[]): number {
  const metrics = gutterMetricsForLine(slots, { ...line, reviewLineNumber: 0 });
  if (metrics) return metrics.top;
  const typeBoost: Record<string, number> = {
    HEADER: 0,
    TRANSACTION: 1000,
    TRANSACTION_SUBTOTAL: 2000,
    PAGE1_SUMMARY: 2100,
    GRAND_TOTAL: 3000,
    LEGEND: 4000,
  };
  return (line.page - 1) * 10000 + (typeBoost[line.rowType] ?? 5000);
}

/** Merge fuel_bvd logical rows with unmapped PDF fields; renumber by page + vertical position. */
export function buildReviewLogicalRowsMerged(
  rows: FuelBvdRow[],
  unmapped: BvdUnmappedSourceField[],
  slots: BvdFieldSlot[],
): BvdReviewLogicalRow[] {
  const base = buildReviewLogicalRows(rows);
  const drafts: LogicalDraft[] = base.map(({ reviewLineNumber: _n, ...rest }) => ({
    ...rest,
    sortTop: estimateSortTop(rest, slots),
  }));

  for (const u of unmapped) {
    drafts.push({
      fuelBvdId: 0,
      rowType: "UNMAPPED_SOURCE",
      page: u.page,
      label: u.label,
      unmappedId: u.id,
      sortTop: u.top,
    });
  }

  drafts.sort((a, b) => a.page - b.page || (a.sortTop ?? 0) - (b.sortTop ?? 0));
  return drafts.map((d, i) => ({ ...d, reviewLineNumber: i + 1 }));
}

export function reviewLineForSelection(
  lines: BvdReviewLogicalRow[],
  fuelBvdId: number,
  fieldName: string,
  rowType: string,
): number | null {
  if (rowType === "HEADER") {
    return lines.find((l) => l.fuelBvdId === fuelBvdId && l.headerField === fieldName)?.reviewLineNumber ?? null;
  }
  return lines.find((l) => l.fuelBvdId === fuelBvdId && !l.headerField)?.reviewLineNumber ?? null;
}

export function reviewLineForUnmapped(lines: BvdReviewLogicalRow[], unmappedId: string): number | null {
  return lines.find((l) => l.unmappedId === unmappedId)?.reviewLineNumber ?? null;
}

export function gutterMetricsForLine(
  slots: BvdFieldSlot[],
  line: BvdReviewLogicalRow,
  unmapped?: BvdUnmappedSourceField[],
): { top: number; height: number } | null {
  if (line.rowType === "UNMAPPED_SOURCE" && line.unmappedId && unmapped) {
    const u = unmapped.find((x) => x.id === line.unmappedId);
    if (u) return { top: u.top, height: Math.max(u.height, 28) };
  }
  const rowSlots = slots.filter((s) => {
    if (s.fuelBvdId !== line.fuelBvdId) return false;
    if (line.headerField) return s.fieldName === line.headerField;
    return true;
  });
  if (!rowSlots.length) return null;
  const top = Math.min(...rowSlots.map((s) => s.top));
  const bottom = Math.max(...rowSlots.map((s) => s.top + s.height));
  return { top, height: Math.max(bottom - top, 14) };
}

export function linesOnPage(lines: BvdReviewLogicalRow[], page: number): BvdReviewLogicalRow[] {
  return lines.filter((l) => l.page === page);
}

export function formatReviewLineNumber(n: number): string {
  return String(n).padStart(2, "0");
}
