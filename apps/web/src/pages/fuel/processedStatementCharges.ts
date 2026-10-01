import type { FuelBvdRow } from "../../api";

export type ProcessedStatementChargeSections = {
  cardTransactions: FuelBvdRow[];
  expressCharges: FuelBvdRow[];
  chargeCount: number;
};

/** Accepted charge rows for processed operational workspace (excludes control/subtotal rows). */
export function splitProcessedStatementCharges(rows: FuelBvdRow[]): ProcessedStatementChargeSections {
  const cardTransactions = rows.filter((r) => r.row_type === "TRANSACTION");
  const expressCharges = rows.filter((r) => r.row_type === "EXPRESS_TRANSACTION");
  return {
    cardTransactions,
    expressCharges,
    chargeCount: cardTransactions.length + expressCharges.length,
  };
}

export function allProcessedStatementSearchableRows(sections: ProcessedStatementChargeSections): FuelBvdRow[] {
  return [...sections.cardTransactions, ...sections.expressCharges];
}
