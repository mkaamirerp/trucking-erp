import { describe, expect, it } from "vitest";
import type { FuelProcessedOperationalTransaction } from "../../api";
import { resolveManualProcessedSourceDetailFields } from "./manualProcessedSourceDetailsFields";

function lovesOperational(): FuelProcessedOperationalTransaction {
  return {
    id: 1,
    batch_id: 12,
    source_row_order: 1,
    source_row_id: "stage",
    source_vendor: "MANUAL_ENTRY",
    transaction_date: "2026-09-12",
    transaction_datetime_source: "2026-09-12",
    transaction_timezone_source: "DATE_ONLY",
    unit_number_snapshot: "1100",
    card_or_account_id: "ending 7145",
    driver_name_snapshot: null,
    driver_id: null,
    truck_id: null,
    owner_operator_payee_id: null,
    city: "Summerton",
    province_state: "SC",
    country: null,
    merchant_site: "Love's",
    site_number: "790",
    site_name: "Love's",
    provider_transaction_identity: "A255392626",
    provider_reference_raw: "99967251",
    provider_raw: {
      entry_method: "RECEIPT",
      pump: "24",
      trailer_number: "13006",
      company_name: "FIRST BASE FREIGHT LTD",
      unit_price_candidates: ["6.089"],
    },
    product: "TRKDS / diesel",
    product_code_raw: "TRKDS / diesel",
    quantity: "172.445",
    quantity_unit: "gallons",
    unit_price: "6.089",
    retail_amount: "6.089",
    pre_tax_amount: "1050.0200",
    provider_discount_amount: null,
    gst_amount: null,
    hst_amount: null,
    pst_amount: null,
    qst_amount: null,
    total_amount: "1050.0200",
    currency: "USD",
    principal_amount: null,
    provider_fee_amount: null,
    classification: null,
    classification_status: null,
    financial_responsibility: null,
    owner_operator_charge_amount: null,
    settlement_deduction_candidate: null,
    settlement_deduction_basis_amount: null,
  };
}

describe("resolveManualProcessedSourceDetailFields", () => {
  it("prefers operational columns over flat provider_raw for Love's receipt evidence", () => {
    const fields = resolveManualProcessedSourceDetailFields(
      lovesOperational(),
      lovesOperational().provider_raw,
      "41868",
    );
    expect(fields.vendor).toBe("Love's");
    expect(fields.storeNumber).toBe("790");
    expect(fields.receiptTicket).toBe("99967251");
    expect(fields.authorization).toBe("A255392626");
    expect(fields.cardOrAccount).toBe("ending 7145");
    expect(fields.invoiceReference).toBe("41868");
    expect(fields.pump).toBe("24");
    expect(fields.trailer).toBe("13006");
    expect(fields.companyName).toBe("FIRST BASE FREIGHT LTD");
    expect(fields.entryMethod).toBe("RECEIPT");
    expect(fields.priceCandidates).toBe("6.089");
  });

  it("falls back to provider_raw when operational reference fields are empty", () => {
    const op = lovesOperational();
    op.provider_reference_raw = null;
    op.provider_transaction_identity = null;
    op.site_number = null;
    const fields = resolveManualProcessedSourceDetailFields(op, {
      store_number: "790",
      receipt_ticket_number: "99967251",
      authorization_number: "A255392626",
      invoice_reference: "41868",
    });
    expect(fields.storeNumber).toBe("790");
    expect(fields.receiptTicket).toBe("99967251");
    expect(fields.authorization).toBe("A255392626");
    expect(fields.invoiceReference).toBe("41868");
  });
});
