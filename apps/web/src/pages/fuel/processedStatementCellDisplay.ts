import type { FuelBvdRow } from "../../api";
import { isProviderMoneyDashLike } from "./fuelProviderMoneyDisplay";
import { operationalCell } from "../fuelBvdReview/bvdParsedDisplay";
import {
  formatBvdProviderMoneyField,
  isBvdProviderMoneyField,
} from "../fuelBvdReview/bvdMoneyDisplay";

/** Per-unit prices keep provider precision (BVD 4dp; Nationwide ex-GST). */
const PROCESSED_UNIT_PRICE_FIELDS = new Set(["retail", "billed", "disc_rate"]);

export function formatProcessedUnitPriceField(raw: string): string {
  if (isProviderMoneyDashLike(raw)) return "0.00";
  return raw.trim();
}

/** TruckERP processed statement grid (all providers) — presentation only. */
export function processedStatementCellDisplay(row: FuelBvdRow, field: string): string {
  const raw = operationalCell(row, field);
  if (PROCESSED_UNIT_PRICE_FIELDS.has(field)) {
    return formatProcessedUnitPriceField(raw);
  }
  if (isBvdProviderMoneyField(field)) {
    return formatBvdProviderMoneyField(raw);
  }
  const t = raw.trim();
  return t || "—";
}
