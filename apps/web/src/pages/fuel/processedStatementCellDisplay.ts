import type { FuelBvdRow } from "../../api";
import { operationalCell } from "../fuelBvdReview/bvdParsedDisplay";
import {
  formatBvdProviderMoneyField,
  isBvdProviderMoneyField,
} from "../fuelBvdReview/bvdMoneyDisplay";

/** TruckERP processed statement grid (all providers) — presentation only. */
export function processedStatementCellDisplay(row: FuelBvdRow, field: string): string {
  const raw = operationalCell(row, field);
  if (isBvdProviderMoneyField(field)) {
    return formatBvdProviderMoneyField(raw);
  }
  const t = raw.trim();
  return t || "—";
}
