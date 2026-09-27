import type { FuelBvdRow } from "../../api";
import { BVD_SECTION_ORDER } from "../fuelBvdReviewLabels";

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
