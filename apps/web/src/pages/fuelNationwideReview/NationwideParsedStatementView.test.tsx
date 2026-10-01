import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import type { FuelNationwideRow } from "../../api";
import NationwideParsedStatementView from "./NationwideParsedStatementView";

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function txn(i: number): FuelNationwideRow {
  return {
    id: i,
    import_id: "eab57e99-c4bf-40e3-ba2e-21141729a8d8",
    row_type: "TRANSACTION",
    card_number: "XXXXX07588",
    product: i % 3 === 0 ? "SCALE" : i % 2 === 0 ? "REEFER" : "DIESEL",
    total: "100.00",
    currency: "USD",
  };
}

describe("NationwideParsedStatementView", () => {
  it("renders 12 purchase rows and 14 controls", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    const rows: FuelNationwideRow[] = [
      {
        id: 0,
        import_id: "eab57e99-c4bf-40e3-ba2e-21141729a8d8",
        row_type: "HEADER",
        invoice_number: "20250522B-06142026",
        account_code: "20250522B",
      },
      ...Array.from({ length: 12 }, (_, i) => txn(i + 1)),
      ...Array.from({ length: 14 }, (_, i) => ({
        id: 100 + i,
        import_id: "eab57e99-c4bf-40e3-ba2e-21141729a8d8",
        row_type: "CONTROL",
        control_type: "TAX_CONTROL",
        row_label: "GST",
      })),
    ];
    await act(async () => {
      root.render(
        <NationwideParsedStatementView
          rows={rows}
          statusLabel="Processed"
          onOpenPdf={() => undefined}
          sourceReconciliation={{ passed: true, checks: [] }}
        />,
      );
    });
    expect(container.textContent).toContain("Purchases (12)");
    expect(container.textContent).toContain("Provider controls (14)");
    expect(container.querySelectorAll(".bvd-statement__table--nationwide tbody tr").length).toBe(12);
  });
});
