import type { FuelBvdRow, FuelNationwideRow } from "../../api";

/**
 * Nationwide → shared processed-statement row list.
 *
 * `FuelBvdRow` is a legacy API/DTO name (parsed import line items). The same shape powers
 * ProcessedStatementWorkspace / BvdTransactionRowsTable for BVD, Nationwide, and future providers.
 * This module is Nationwide-only mapping — not BVD business logic.
 */

function nationwideDiscountAmount(row: FuelNationwideRow): string {
  const usa = row.usa_discount?.trim();
  if (usa) return usa;
  const missed = row.missed_disc?.trim();
  if (missed) return missed;
  return "";
}

export function adaptNationwideImportRowsForProcessedStatement(
  rows: FuelNationwideRow[],
): FuelBvdRow[] {
  const header = rows.find((r) => r.row_type === "HEADER");
  const fallbackCard = header?.card_number?.trim() || "";
  return rows
    .filter((r) => r.row_type === "TRANSACTION")
    .map((r) => {
      const unitPrice = r.ex_gst_per_unit?.trim() || "";
      return {
        id: r.id,
        import_id: r.import_id,
        row_type: "TRANSACTION",
        card_number: r.card_number?.trim() || fallbackCard,
        unit_number: r.unit_number,
        transaction_date: r.transaction_date,
        site_city: r.city,
        prov_st: r.prov_st,
        prod: r.product,
        qty: r.volume,
        retail: unitPrice,
        billed: unitPrice,
        disc_amt: nationwideDiscountAmount(r),
        final_amt: r.total,
        cur: r.currency,
      };
    });
}
