import type { FuelBvdRow, FuelNationwideRow } from "../../api";

/**
 * Nationwide → shared processed-statement row list.
 *
 * `FuelBvdRow` is a legacy API/DTO name (parsed import line items). The same shape powers
 * ProcessedStatementWorkspace / BvdTransactionRowsTable for BVD, Nationwide, and future providers.
 * This module is Nationwide-only mapping — not BVD business logic.
 */

export function adaptNationwideImportRowsForProcessedStatement(
  rows: FuelNationwideRow[],
): FuelBvdRow[] {
  const header = rows.find((r) => r.row_type === "HEADER");
  const fallbackCard = header?.card_number?.trim() || "";
  return rows
    .filter((r) => r.row_type === "TRANSACTION")
    .map((r) => {
      const unitPrice = r.ex_gst_per_unit?.trim() || "";
      const usaDiscount = r.usa_discount?.trim() || "";
      const missedDisc = r.missed_disc?.trim() || "";
      const oonFees = r.oon_fees?.trim() || "";
      const providerExtras = [
        usaDiscount ? `USA Discount: ${usaDiscount}` : "",
        missedDisc ? `Missed Disc: ${missedDisc}` : "",
        oonFees && oonFees !== "-" && oonFees !== "—" ? `OON Fees: ${oonFees}` : "",
      ]
        .filter(Boolean)
        .join(" · ");
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
        // Nationwide has Ex-GST ($/U), not BVD retail vs billed spread — do not duplicate into both.
        retail: "",
        billed: unitPrice,
        disc_amt: "",
        final_amt: r.total,
        cur: r.currency,
        notes_raw: providerExtras || null,
      };
    });
}
