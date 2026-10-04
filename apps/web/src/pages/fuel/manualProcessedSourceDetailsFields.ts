import type { FuelProcessedOperationalTransaction } from "../../api";

export type ManualProcessedSourceDetailFields = {
  entryMethod: string | null;
  vendor: string | null;
  storeNumber: string | null;
  receiptTicket: string | null;
  authorization: string | null;
  cardOrAccount: string | null;
  invoiceReference: string | null;
  pump: string | null;
  trailer: string | null;
  companyName: string | null;
  vehicleIdEvidence: string | null;
  taxNote: string | null;
  priceCandidates: string | null;
  rejectedPrices: string | null;
};

function trimOrNull(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value).trim();
  return text ? text : null;
}

function invoiceFromSummary(invoiceNumber: string | null | undefined): string | null {
  const text = trimOrNull(invoiceNumber);
  if (!text || text === "—") return null;
  return text;
}

/** Canonical/operational first; provider_raw only for evidence without columns. */
export function resolveManualProcessedSourceDetailFields(
  operational: FuelProcessedOperationalTransaction | null | undefined,
  providerRaw: Record<string, unknown> | null | undefined,
  invoiceNumber?: string | null,
): ManualProcessedSourceDetailFields {
  const raw = providerRaw ?? {};
  const op = operational;

  const vendor =
    trimOrNull(op?.merchant_site) ?? trimOrNull(op?.site_name) ?? null;
  const storeNumber = trimOrNull(op?.site_number) ?? trimOrNull(raw.store_number);
  const receiptTicket =
    trimOrNull(op?.provider_reference_raw) ?? trimOrNull(raw.receipt_ticket_number);
  const authorization =
    trimOrNull(op?.provider_transaction_identity) ?? trimOrNull(raw.authorization_number);
  const cardOrAccount = trimOrNull(op?.card_or_account_id);
  const invoiceReference =
    invoiceFromSummary(invoiceNumber) ?? trimOrNull(raw.invoice_reference);

  const candidates = Array.isArray(raw.unit_price_candidates)
    ? (raw.unit_price_candidates as string[]).map((c) => String(c).trim()).filter(Boolean)
    : [];
  const rejected = Array.isArray(raw.unit_price_candidates_rejected)
    ? (raw.unit_price_candidates_rejected as string[]).map((c) => String(c).trim()).filter(Boolean)
    : [];

  return {
    entryMethod: trimOrNull(raw.entry_method),
    vendor,
    storeNumber,
    receiptTicket,
    authorization,
    cardOrAccount,
    invoiceReference,
    pump: trimOrNull(raw.pump),
    trailer: trimOrNull(raw.trailer_number),
    companyName: trimOrNull(raw.company_name),
    vehicleIdEvidence: trimOrNull(raw.vehicle_id_source_evidence),
    taxNote: trimOrNull(raw.tax_included_note),
    priceCandidates: candidates.length > 0 ? candidates.join(", ") : null,
    rejectedPrices: rejected.length > 0 ? rejected.join(", ") : null,
  };
}
