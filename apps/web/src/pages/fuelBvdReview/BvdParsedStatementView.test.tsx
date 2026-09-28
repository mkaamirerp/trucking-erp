import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdRow } from "../../api";
import { BVD_TRANSACTION_COLUMNS } from "../fuelBvdReviewLabels";
import BvdParsedStatementView from "./BvdParsedStatementView";

function row(partial: Partial<FuelBvdRow> & Pick<FuelBvdRow, "id" | "row_type">): FuelBvdRow {
  return {
    import_id: "imp-1",
    ...partial,
  } as FuelBvdRow;
}

describe("BvdParsedStatementView purchases table", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function renderPurchases(rows: FuelBvdRow[]) {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <BvdParsedStatementView
          rows={rows}
          statusLabel="Pending"
          onOpenPdf={vi.fn()}
          sourceReconciliation={{
            passed: true,
            transaction_total: "10.00",
            all_unit_total: "10.00",
            provider_grand_total: "10.00",
            difference: "0.00",
            checks: [],
          }}
        />,
      );
    });
  }

  it("A/B: renders all BVD_TRANSACTION_COLUMNS on purchases (processing review)", () => {
    renderPurchases([
      row({ id: 1, row_type: "HEADER", invoice_number: "972201", card_number: "4237111" }),
      row({
        id: 2,
        row_type: "TRANSACTION",
        auth_code: "A1",
        prod: "TA",
        gst: "0.00",
        final_amt: "10.00",
      }),
    ]);
    const purchases = container.querySelector('[data-testid="bvd-purchases-full-table"]');
    expect(purchases).toBeTruthy();
    expect(container.querySelector(".bvd-txn-rows")).toBeNull();
    const headers = purchases?.querySelectorAll("thead th");
    expect(headers?.length).toBe(BVD_TRANSACTION_COLUMNS.length);
    for (const col of BVD_TRANSACTION_COLUMNS) {
      expect(purchases?.textContent).toContain(col.label);
    }
    expect(purchases?.textContent).toContain("0.00");
    expect(purchases?.textContent).toContain("TA");
  });

  it("B: full-stored-detail mode uses the same 21-column purchases grid", () => {
    renderPurchases([
      row({ id: 1, row_type: "HEADER", invoice_number: "972201" }),
      row({ id: 2, row_type: "TRANSACTION", gst: "0.00", disc_rate: "0.0000" }),
    ]);
    act(() => {
      root.render(
        <BvdParsedStatementView
          rows={[
            row({ id: 1, row_type: "HEADER", invoice_number: "972201" }),
            row({ id: 2, row_type: "TRANSACTION", gst: "0.00", disc_rate: "0.0000" }),
          ]}
          statusLabel="Completed"
          onOpenPdf={vi.fn()}
          presentation="full-stored-detail"
          sourceReconciliation={{
            passed: true,
            transaction_total: "0",
            all_unit_total: "0",
            provider_grand_total: "0",
            difference: "0.00",
            checks: [],
          }}
        />,
      );
    });
    const purchases = container.querySelector('[data-testid="bvd-purchases-full-table"]');
    expect(purchases?.querySelectorAll("thead th").length).toBe(BVD_TRANSACTION_COLUMNS.length);
    expect(container.textContent).toContain("Disc Rate");
    expect(container.textContent).toContain("GST");
  });
});
