import type { FuelBvdRow, FuelProcessedOperationalTransaction } from "../../api";
import { operationalCell } from "../fuelBvdReview/bvdParsedDisplay";
import { processedStatementCellDisplay } from "./processedStatementCellDisplay";

/** Compact grid unit suffix (canonical uses litres / gallons). */
export function abbreviateFuelQuantityUnit(unit: string | null | undefined): string | null {
  const t = (unit ?? "").trim().toLowerCase();
  if (!t) return null;
  if (t === "litres" || t === "liter" || t === "liters" || t === "l") return "L";
  if (t === "gallons" || t === "gallon" || t === "gal") return "gal";
  return unit!.trim();
}

export function inferFuelQuantityUnitFromCurrency(currencyRaw: string): string | null {
  const c = currencyRaw.trim().toUpperCase();
  if (c === "CN" || c === "CAD") return "L";
  if (c === "US" || c === "USD") return "gal";
  return null;
}

export function resolveFuelTxnQuantityUnit(row: FuelBvdRow): string | null {
  const explicit = abbreviateFuelQuantityUnit(row.quantity_unit);
  if (explicit) return explicit;
  return inferFuelQuantityUnitFromCurrency(operationalCell(row, "cur"));
}

/** Main grid: `674.17 L` — quantity and unit always shown together when qty exists. */
export function formatFuelTxnQuantityWithUnit(row: FuelBvdRow): string {
  const qtyRaw = operationalCell(row, "qty").trim();
  if (!qtyRaw) return "—";
  const qty = processedStatementCellDisplay(row, "qty");
  const unit = resolveFuelTxnQuantityUnit(row);
  return unit ? `${qty} ${unit}` : qty;
}

export function applyOperationalQuantityUnitToStatementRows(
  rows: FuelBvdRow[],
  operational: FuelProcessedOperationalTransaction[],
): FuelBvdRow[] {
  if (!operational.length) return rows;
  const bySourceId = new Map<string, FuelProcessedOperationalTransaction>();
  for (const op of operational) {
    const sid = op.source_row_id?.trim();
    if (sid) bySourceId.set(sid, op);
  }
  return rows.map((row) => {
    const op = bySourceId.get(String(row.id));
    if (!op?.quantity_unit) return row;
    return { ...row, quantity_unit: op.quantity_unit };
  });
}
