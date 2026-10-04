import type { FuelBvdRow, FuelProcessedOperationalTransaction } from "../../api";

function moneyCell(value: string | null | undefined): string {
  const t = (value ?? "").trim();
  return t;
}

function unitPriceCell(value: string | null | undefined): string {
  const t = (value ?? "").trim();
  return t;
}

/**
 * Manual entry → shared processed-statement row shape (`FuelBvdRow` legacy DTO name).
 * Uses provider-neutral `operational_transactions` only (no staging tables).
 */
export function adaptManualOperationalTransactionsForProcessedStatement(
  operational: FuelProcessedOperationalTransaction[],
  sourceImportRef: string | null,
): FuelBvdRow[] {
  return operational.map((txn) => ({
    id: txn.id,
    import_id: sourceImportRef ?? String(txn.batch_id),
    row_type: "TRANSACTION",
    card_number: txn.card_or_account_id,
    unit_number: txn.unit_number_snapshot,
    transaction_date: txn.transaction_date,
    driver_name: txn.driver_name_snapshot,
    site_name: txn.site_name ?? txn.merchant_site,
    site_number: txn.site_number,
    site_city: txn.city,
    prov_st: txn.province_state,
    prod: txn.product ?? txn.product_code_raw,
    qty: txn.quantity,
    quantity_unit: txn.quantity_unit,
    retail: unitPriceCell(txn.retail_amount ?? txn.unit_price),
    billed: unitPriceCell(txn.unit_price ?? txn.retail_amount),
    disc_amt: moneyCell(txn.provider_discount_amount),
    pre_tax_amt: moneyCell(txn.pre_tax_amount),
    gst: moneyCell(txn.gst_amount),
    hst: moneyCell(txn.hst_amount),
    pst: moneyCell(txn.pst_amount),
    qst: moneyCell(txn.qst_amount),
    final_amt: moneyCell(txn.total_amount),
    cur: txn.currency,
  }));
}
