import type { FuelBvdRow, FuelNationwideRow, FuelNationwideSourceReconciliation } from "../../api";
import { splitProcessedStatementCharges } from "./processedStatementCharges";

export type FuelDashboardImportRows = {
  sourceRows: FuelBvdRow[];
  cardTransactions: FuelBvdRow[];
  expressCharges: FuelBvdRow[];
  chargeCount: number;
  cardNumber: string;
  nationwideRows?: FuelNationwideRow[];
  nationwideReconciliation?: FuelNationwideSourceReconciliation | null;
};

export function parseBvdImportRowsForDashboard(rows: FuelBvdRow[]): FuelDashboardImportRows {
  const header = rows.find((r) => r.row_type === "HEADER");
  const { cardTransactions, expressCharges, chargeCount } = splitProcessedStatementCharges(rows);
  const cardNumber =
    header && header.card_number != null && header.card_number !== ""
      ? String(header.card_number)
      : "";
  return {
    sourceRows: rows,
    cardTransactions,
    expressCharges,
    chargeCount,
    cardNumber,
  };
}
