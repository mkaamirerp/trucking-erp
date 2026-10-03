import type { FuelBvdRow, FuelNationwideRow } from "../../api";

function nationwideDiscountAmount(row: FuelNationwideRow): string {
  const usa = row.usa_discount?.trim();
  if (usa) return usa;
  const missed = row.missed_disc?.trim();
  if (missed) return missed;
  return "";
}

/** Map Nationwide TRANSACTION rows into BVD-shaped operational rows (shared TruckERP workspace). */
export function nationwideTransactionsToOperationalBvdRows(rows: FuelNationwideRow[]): FuelBvdRow[] {
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
