import { describe, expect, it } from "vitest";
import type { FuelProcessedOperationalTransaction } from "../../api";
import { adaptManualOperationalTransactionsForProcessedStatement } from "./manualProcessedStatementAdapter";

function txn(partial: Partial<FuelProcessedOperationalTransaction>): FuelProcessedOperationalTransaction {
  return {
    id: 1,
    batch_id: 12,
    source_row_order: 1,
    source_row_id: "stage-1",
    source_vendor: "MANUAL_ENTRY",
    transaction_date: "2026-10-04",
    transaction_datetime_source: "2026-10-04",
    transaction_timezone_source: "DATE_ONLY",
    unit_number_snapshot: "1100",
    card_or_account_id: null,
    driver_name_snapshot: null,
    driver_id: null,
    truck_id: null,
    owner_operator_payee_id: null,
    city: null,
    province_state: null,
    country: null,
    merchant_site: null,
    site_number: null,
    site_name: null,
    provider_raw: {},
    product: "DIESEL",
    product_code_raw: "DIESEL",
    quantity: null,
    quantity_unit: null,
    unit_price: null,
    retail_amount: null,
    pre_tax_amount: null,
    provider_discount_amount: null,
    gst_amount: null,
    hst_amount: null,
    pst_amount: null,
    qst_amount: null,
    total_amount: "500.00",
    currency: "CAD",
    principal_amount: null,
    provider_fee_amount: null,
    classification: null,
    classification_status: null,
    financial_responsibility: null,
    owner_operator_charge_amount: null,
    settlement_deduction_candidate: null,
    settlement_deduction_basis_amount: null,
    ...partial,
  };
}

describe("adaptManualOperationalTransactionsForProcessedStatement", () => {
  it("maps sparse DIRECT-style operational row for shared grid", () => {
    const [row] = adaptManualOperationalTransactionsForProcessedStatement(
      [txn({})],
      "stage-uuid",
    );
    expect(row.row_type).toBe("TRANSACTION");
    expect(row.unit_number).toBe("1100");
    expect(row.prod).toBe("DIESEL");
    expect(row.final_amt).toBe("500.00");
    expect(row.cur).toBe("CAD");
    expect(row.qty).toBeNull();
    expect(row.billed).toBe("");
    expect(row.pre_tax_amt).toBe("");
  });

  it("maps receipt-rich manual operational row", () => {
    const [row] = adaptManualOperationalTransactionsForProcessedStatement(
      [
        txn({
          driver_name_snapshot: "Alex",
          city: "Summerton",
          province_state: "SC",
          merchant_site: "Love's",
          quantity: "172.445",
          quantity_unit: "gallons",
          unit_price: "6.089",
          pre_tax_amount: "1050.02",
          provider_discount_amount: "0.00",
          gst_amount: "0.00",
          card_or_account_id: "ending 7145",
        }),
      ],
      "stage-uuid",
    );
    expect(row.driver_name).toBe("Alex");
    expect(row.site_city).toBe("Summerton");
    expect(row.qty).toBe("172.445");
    expect(row.billed).toBe("6.089");
    expect(row.pre_tax_amt).toBe("1050.02");
    expect(row.disc_amt).toBe("0.00");
    expect(row.gst).toBe("0.00");
  });
});
