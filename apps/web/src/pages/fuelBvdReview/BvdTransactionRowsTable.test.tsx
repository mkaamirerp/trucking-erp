import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import BvdTransactionRowsTable from "./BvdTransactionRowsTable";

function txn(id: number, partial: Partial<FuelBvdRow> = {}): FuelBvdRow {
  return {
    id,
    import_id: "imp",
    row_type: "TRANSACTION",
    transaction_date: "2026-07-23 02:17:56",
    unit_number: "1100",
    driver_name: "JASPREET CHOKAR",
    site_name: "BOWMANVILLE",
    site_city: "BOWMANVILLE",
    prov_st: "ON",
    prod: "TA",
    qty: "719.50",
    retail: "2.2390",
    billed: "2.2390",
    pre_tax_amt: "1,425.63",
    hst: "185.33",
    gst: "0.00",
    pst: "0.00",
    qst: "0.00",
    disc_amt: "0.00",
    final_amt: "1,610.96",
    cur: "CN",
    auth_code: "A204040667-TA",
    site_number: "54228",
    ...partial,
  } as FuelBvdRow;
}

describe("BvdTransactionRowsTable", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function renderTable(rows: FuelBvdRow[]) {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<BvdTransactionRowsTable transactions={rows} cardNumber="4237111" />);
    });
  }

  function headerText(): string {
    return container.querySelector("thead")?.textContent ?? "";
  }

  it("A: main row columns only in header", () => {
    renderTable([txn(1)]);
    const h = headerText();
    expect(h).toMatch(/Date \/ Time/);
    expect(h).toMatch(/Source driver/);
    expect(h).toMatch(/Final amount/);
  });

  it("operational product uses reviewed correction (DF extracted → S / Scale)", () => {
    renderTable([
      txn(1, {
        prod: "DF",
        field_corrections: {
          prod: { extracted_value: "DF", reviewed_value: "S" },
        },
      }),
    ]);
    const productCell = container.querySelector('[data-testid="bvd-txn-col-product"]');
    expect(productCell?.textContent).toContain("Scale");
    expect(productCell?.textContent).not.toContain("DEF");
  });

  it("B: main table does not expose auth, tax, or retail columns", () => {
    renderTable([txn(1)]);
    const h = headerText();
    expect(h).not.toMatch(/Auth Code/i);
    expect(h).not.toMatch(/HST/i);
    expect(h).not.toMatch(/Retail/i);
    expect(h).not.toMatch(/Site #/i);
    expect(container.textContent).not.toContain("A204040667-TA");
  });

  it("C–K: expand, taxes, collapse", () => {
    renderTable([txn(1)]);
    const row = container.querySelector('[data-testid="bvd-txn-row-1"]') as HTMLElement;
    expect(row.getAttribute("data-expanded")).toBe("false");
    expect(container.querySelector('[data-testid="bvd-txn-detail-1"]')).toBeNull();

    act(() => {
      row.click();
    });
    expect(row.getAttribute("data-expanded")).toBe("true");
    const detail = container.querySelector('[data-testid="bvd-txn-detail-1"]');
    expect(detail).not.toBeNull();
    expect(detail?.textContent).toContain("A204040667-TA");
    expect(detail?.textContent).toContain("Site # 54228");
    expect(detail?.querySelector('[data-testid="bvd-txn-tax-hst"]')?.textContent).toMatch(/HST/);
    expect(detail?.querySelector('[data-testid="bvd-txn-tax-gst"]')).toBeNull();
    expect(detail?.textContent).not.toMatch(/Discount/);

    act(() => {
      row.click();
    });
    expect(container.querySelector('[data-testid="bvd-txn-detail-1"]')).toBeNull();
  });

  it("G: non-zero discount in expanded panel", () => {
    renderTable([txn(1, { disc_amt: "5.00" })]);
    const row = container.querySelector('[data-testid="bvd-txn-row-1"]') as HTMLElement;
    act(() => row.click());
    expect(container.querySelector('[data-testid="bvd-txn-discount"]')?.textContent).toBe("5.00");
  });

  it("I: differing retail shown when expanded", () => {
    renderTable([txn(1, { retail: "2.50", billed: "2.39" })]);
    const row = container.querySelector('[data-testid="bvd-txn-row-1"]') as HTMLElement;
    act(() => row.click());
    const detail = container.querySelector('[data-testid="bvd-txn-detail-1"]');
    expect(detail?.textContent).toMatch(/Retail price/);
    expect(detail?.textContent).toContain("2.50");
    expect(detail?.textContent).toContain("2.39");
  });

  it("main row shows Fuel for TA", () => {
    renderTable([txn(1)]);
    expect(container.querySelector('[data-testid="bvd-txn-col-product"]')?.textContent).toBe("Fuel");
  });
});
