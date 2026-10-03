import type { FuelBvdRow, FuelCanonicalTransaction, FuelNationwideRow } from "../../api";
import { parseBvdMoneyString } from "../fuelBvdReview/bvdParsedValidation";

/**
 * Nationwide → shared processed-statement row list.
 *
 * `FuelBvdRow` is a legacy API/DTO name (parsed import line items). The same shape powers
 * ProcessedStatementWorkspace / BvdTransactionRowsTable for BVD, Nationwide, and future providers.
 * This module is Nationwide-only mapping — not BVD business logic.
 */

function formatNationwideUnitPrice(value: number): string {
  const rounded = Math.round(value * 1_000_000) / 1_000_000;
  return rounded.toFixed(6).replace(/\.?0+$/, "") || "0";
}

/** Same rule as backend: retail = billed + (line usa discount / volume). */
export function deriveNationwideRetailUnitPriceFromSource(
  billedUnit: string,
  volume: string,
  usaDiscountTotal: string,
): string {
  const billed = parseBvdMoneyString(billedUnit);
  const qty = parseBvdMoneyString(volume);
  if (billed === null || qty === null || qty === 0) return "";
  const trimmed = usaDiscountTotal.trim();
  if (trimmed === "") return "";
  const discount = parseBvdMoneyString(trimmed);
  if (discount === null) return "";
  if (discount === 0) return billedUnit.trim();
  return formatNationwideUnitPrice(billed + discount / qty);
}

function nationwideStatementPriceFields(
  r: Pick<FuelNationwideRow, "ex_gst_per_unit" | "volume" | "usa_discount">,
): { retail: string; billed: string; disc_amt: string } {
  const billed = r.ex_gst_per_unit?.trim() || "";
  const disc_amt = r.usa_discount?.trim() || "";
  const retail = billed
    ? deriveNationwideRetailUnitPriceFromSource(billed, r.volume?.trim() || "", disc_amt)
    : "";
  return { retail, billed, disc_amt };
}

export function applyNationwideCanonicalPricesToStatementRows(
  rows: FuelBvdRow[],
  canonical: FuelCanonicalTransaction[],
): FuelBvdRow[] {
  if (!canonical.length) return rows;
  const bySourceRowId = new Map<string, FuelCanonicalTransaction>();
  for (const c of canonical) {
    const sid = c.source_row_id?.trim();
    if (sid) bySourceRowId.set(sid, c);
  }
  return rows.map((row) => {
    const c = bySourceRowId.get(String(row.id));
    if (!c) return row;
    const retail = c.retail_amount?.trim() || row.retail || "";
    const billed =
      c.billed_amount?.trim() || c.unit_price?.trim() || row.billed || "";
    const disc_amt = c.provider_discount_amount?.trim() || row.disc_amt || "";
    return { ...row, retail, billed, disc_amt };
  });
}

export function adaptNationwideImportRowsForProcessedStatement(
  rows: FuelNationwideRow[],
): FuelBvdRow[] {
  const header = rows.find((r) => r.row_type === "HEADER");
  const fallbackCard = header?.card_number?.trim() || "";
  return rows
    .filter((r) => r.row_type === "TRANSACTION")
    .map((r) => {
      const { retail, billed, disc_amt } = nationwideStatementPriceFields(r);
      const missedDisc = r.missed_disc?.trim() || "";
      const oonFees = r.oon_fees?.trim() || "";
      const providerExtras = [
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
        retail,
        billed,
        disc_amt,
        final_amt: r.total,
        cur: r.currency,
        notes_raw: providerExtras || null,
      };
    });
}
