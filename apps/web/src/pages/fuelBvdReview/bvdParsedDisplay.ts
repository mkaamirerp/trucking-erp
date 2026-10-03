import type { FuelBvdRow } from "../../api";
import { BVD_SECTION_ORDER } from "../fuelBvdReviewLabels";
import {
  bvdParserMoneyBaseline,
  formatBvdProviderMoneyField,
  isBvdProviderMoneyField,
} from "./bvdMoneyDisplay";
import { extractedValue, reviewedValue, type DraftMap } from "./bvdReviewValues";

export {
  BVD_PROVIDER_MONEY_FIELDS,
  bvdParserMoneyBaseline,
  formatBvdProviderMoneyField,
  isBvdProviderMoneyField,
} from "./bvdMoneyDisplay";

const TYPE_RANK: Record<string, number> = Object.fromEntries(BVD_SECTION_ORDER.map((t, i) => [t, i]));

export function sortBvdRows(rows: FuelBvdRow[]): FuelBvdRow[] {
  return [...rows].sort((a, b) => {
    const pa = a.source_page ?? 1;
    const pb = b.source_page ?? 1;
    if (pa !== pb) return pa - pb;
    const ta = TYPE_RANK[a.row_type] ?? 99;
    const tb = TYPE_RANK[b.row_type] ?? 99;
    if (ta !== tb) return ta - tb;
    return (a.source_row_number ?? 0) - (b.source_row_number ?? 0);
  });
}

export function displayCell(row: FuelBvdRow, field: string): string {
  const v = row[field as keyof FuelBvdRow];
  if (v === null || v === undefined || v === "") return "";
  return String(v);
}

/** Finalized/reviewed operational value for Fuel UI (parser column + correction overlay). */
export function operationalCell(row: FuelBvdRow, field: string): string {
  const reviewed = row.field_corrections?.[field]?.reviewed_value;
  if (reviewed !== undefined && reviewed !== null && String(reviewed).length > 0) {
    return String(reviewed);
  }
  return displayCell(row, field);
}

/** Review/processing UI display for one field (effective + zero-as-0.00 money formatting). */
export function bvdReviewFieldDisplay(row: FuelBvdRow, field: string, drafts: DraftMap = {}): string {
  const raw = reviewedValue(row, field, drafts) || extractedValue(row, field);
  if (isBvdProviderMoneyField(field)) {
    return formatBvdProviderMoneyField(raw);
  }
  const t = raw.trim();
  return t || "—";
}
