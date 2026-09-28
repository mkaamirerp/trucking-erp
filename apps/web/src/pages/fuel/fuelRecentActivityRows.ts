import type { FuelBvdRow } from "../../api";

export function parseBvdImportRowsForDashboard(rows: FuelBvdRow[]): {
  transactions: FuelBvdRow[];
  cardNumber: string;
} {
  const header = rows.find((r) => r.row_type === "HEADER");
  const transactions = rows.filter((r) => r.row_type === "TRANSACTION");
  const cardNumber =
    header && header.card_number != null && header.card_number !== ""
      ? String(header.card_number)
      : "";
  return { transactions, cardNumber };
}
