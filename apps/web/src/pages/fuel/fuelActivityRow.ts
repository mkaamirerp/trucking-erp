import type { FuelProcessedSummary } from "../../api";

/** Row shape for Fuel Recent Activity formatters (provider-neutral). */
export type FuelActivityRow = {
  provider: string;
  batch_id: number;
  source_import_ref: string | null;
  invoice_number: string;
  review_status: string;
  read_only: boolean;
  processed_at: string | null;
  period_start: string | null;
  period_end: string | null;
  card_number: string | null;
  account_code: string | null;
  purchase_card_count: number;
  purchase_card_numbers: string[];
  due_date: string | null;
  invoice_disc_amt: string;
  total_amount: string;
  currency: string | null;
  cad_transaction_total: string | null;
  usd_transaction_total: string | null;
  usd_provider_control: string | null;
  transaction_count: number;
  control_count: number;
};

export function fuelActivityRowFromProcessed(summary: FuelProcessedSummary): FuelActivityRow {
  return {
    provider: summary.provider_code,
    batch_id: summary.batch_id,
    source_import_ref: summary.source_import_ref,
    invoice_number: summary.invoice_number,
    review_status: summary.review_status,
    read_only: summary.read_only,
    processed_at: summary.finalized_at,
    period_start: summary.period_start,
    period_end: summary.period_end,
    card_number: summary.account_reference,
    account_code: summary.account_reference,
    purchase_card_count: summary.purchase_card_count,
    purchase_card_numbers: summary.purchase_card_numbers,
    due_date: summary.due_date,
    invoice_disc_amt: "",
    total_amount: summary.total_amount,
    currency: summary.currency,
    cad_transaction_total: summary.cad_transaction_total,
    usd_transaction_total: summary.usd_transaction_total,
    usd_provider_control: summary.usd_provider_control,
    transaction_count: summary.transaction_count,
    control_count: summary.control_count,
  };
}
