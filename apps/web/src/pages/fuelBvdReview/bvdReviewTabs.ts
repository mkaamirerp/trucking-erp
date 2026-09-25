import type { FuelBvdRow } from "../../api";
import type { BvdReviewTabId } from "../fuelBvdReviewLabels";

export function rowsForTab(rows: FuelBvdRow[], tab: BvdReviewTabId): FuelBvdRow[] {
  switch (tab) {
    case "HEADER":
      return rows.filter((r) => r.row_type === "HEADER");
    case "TRANSACTIONS":
      return rows.filter((r) => r.row_type === "TRANSACTION");
    case "CONTROLS":
      return rows.filter((r) => r.row_type === "TRANSACTION_SUBTOTAL" || r.row_type === "PAGE1_SUMMARY");
    case "GRAND_TOTAL":
      return rows.filter((r) => r.row_type === "GRAND_TOTAL");
    case "LEGEND":
      return rows.filter((r) => r.row_type === "LEGEND");
    default:
      return [];
  }
}

export function defaultTabForRowType(rowType: string): BvdReviewTabId {
  if (rowType === "HEADER") return "HEADER";
  if (rowType === "TRANSACTION") return "TRANSACTIONS";
  if (rowType === "TRANSACTION_SUBTOTAL" || rowType === "PAGE1_SUMMARY") return "CONTROLS";
  if (rowType === "GRAND_TOTAL") return "GRAND_TOTAL";
  return "LEGEND";
}
