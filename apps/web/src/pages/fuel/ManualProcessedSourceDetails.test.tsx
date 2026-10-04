import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import ManualProcessedSourceDetails from "./ManualProcessedSourceDetails";
import type { FuelProcessedOperationalTransaction } from "../../api";

const lovesOperational: FuelProcessedOperationalTransaction = {
  id: 1,
  batch_id: 12,
  source_row_order: 1,
  source_row_id: "x",
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
  city: null,
  province_state: null,
  country: null,
  merchant_site: "Love's",
  site_number: "790",
  site_name: "Love's",
  provider_transaction_identity: "A255392626",
  provider_reference_raw: "99967251",
  provider_raw: { entry_method: "RECEIPT", pump: "24" },
  product: null,
  product_code_raw: null,
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
  total_amount: null,
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

describe("ManualProcessedSourceDetails", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("renders vendor, store, ticket, auth, and card from operational fields", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <ManualProcessedSourceDetails operational={lovesOperational} invoiceNumber="41868" />,
      );
    });
    const text = container.textContent ?? "";
    expect(text).toContain("Love's");
    expect(text).toContain("790");
    expect(text).toContain("99967251");
    expect(text).toContain("A255392626");
    expect(text).toContain("ending 7145");
    expect(text).toContain("41868");
  });
});
