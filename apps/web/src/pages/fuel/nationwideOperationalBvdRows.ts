import type { FuelBvdRow, FuelNationwideRow } from "../../api";

/** Map Nationwide TRANSACTION rows into BVD-shaped operational rows (shared TruckERP workspace). */
export function nationwideTransactionsToOperationalBvdRows(rows: FuelNationwideRow[]): FuelBvdRow[] {
  const header = rows.find((r) => r.row_type === "HEADER");
  const fallbackCard = header?.card_number?.trim() || "";
  return rows
    .filter((r) => r.row_type === "TRANSACTION")
    .map((r) => ({
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
      final_amt: r.total,
      cur: r.currency,
    }));
}
