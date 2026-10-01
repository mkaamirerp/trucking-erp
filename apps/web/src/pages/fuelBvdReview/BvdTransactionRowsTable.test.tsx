import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import BvdTransactionRowsTable from "./BvdTransactionRowsTable";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../../..");
const fixture972201 = JSON.parse(
  readFileSync(join(repoRoot, "tests/fixtures/fuel_bvd_972201_expected.json"), "utf-8"),
) as { rows: FuelBvdRow[] };
const rows972201 = fixture972201.rows
  .filter((r) => r.row_type === "TRANSACTION")
  .map((r, i) => ({ ...r, id: i + 1, import_id: "972201" })) as FuelBvdRow[];

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

  it("B: main table shows retail/billed but not auth or site # columns", () => {
    renderTable([txn(1)]);
    const h = headerText();
    expect(h).toMatch(/Retail price/);
    expect(h).toMatch(/Billed price/);
    expect(h).not.toMatch(/Auth Code/i);
    expect(h).not.toMatch(/Site #/i);
    expect(container.querySelector('[data-testid="bvd-txn-col-retail"]')?.textContent).toBe("2.2390");
    expect(container.querySelector('[data-testid="bvd-txn-col-billed"]')?.textContent).toBe("2.2390");
    expect(container.textContent).not.toContain("A204040667-TA");
  });

  it("column header row is distinct from body rows", () => {
    renderTable([txn(1)]);
    expect(container.querySelector("thead.bvd-txn-rows__thead tr.bvd-txn-rows__header-row")).not.toBeNull();
    expect(container.querySelector("tbody tr.bvd-txn-rows__main")).not.toBeNull();
    expect(container.querySelector("thead th.bvd-txn-rows__header-cell")).not.toBeNull();
  });

  it("discount column always exists with 0.00 for zero source discount", () => {
    renderTable([txn(1, { disc_amt: "0.00" })]);
    expect(headerText()).toMatch(/Discount/);
    expect(container.querySelector('[data-testid="bvd-txn-col-discount"]')?.textContent).toBe("0.00");
  });

  it("shows HST only when invoice has non-zero HST and hides zero tax types", () => {
    renderTable([txn(1, { hst: "185.33", gst: "0.00", pst: "0.00", qst: "0.00" })]);
    const h = headerText();
    expect(h).toMatch(/HST/);
    expect(h).not.toMatch(/GST/);
    expect(h).not.toMatch(/PST/);
    expect(h).not.toMatch(/QST/);
    expect(container.querySelector('[data-testid="bvd-txn-col-hst"]')?.textContent).toBe("185.33");
    expect(container.querySelector('[data-testid="bvd-txn-col-gst"]')).toBeNull();
  });

  it("972201 fixture shows Discount and HST only in compact headers", () => {
    renderTable(rows972201);
    const wrap = container.querySelector('[data-testid="bvd-txn-rows-table"]');
    expect(wrap?.getAttribute("data-active-tax-columns")).toBe("hst");
    const h = headerText();
    expect(h).toMatch(/Discount/);
    expect(h).toMatch(/HST/);
    expect(h).not.toMatch(/GST/);
    expect(h).not.toMatch(/PST/);
    expect(h).not.toMatch(/QST/);
    expect(container.querySelectorAll('[data-testid="bvd-txn-col-discount"]')[0]?.textContent).toBe(
      "0.00",
    );
  });

  it("838710-like rows show Discount without any tax columns", () => {
    renderTable([
      txn(1, { disc_amt: "44.24", hst: "0.00", gst: "0.00", pst: "0.00", qst: "0.00" }),
      txn(2, { disc_amt: "0.00", hst: "0.00", gst: "0.00", pst: "0.00", qst: "0.00" }),
    ]);
    expect(container.querySelector('[data-testid="bvd-txn-rows-table"]')?.getAttribute("data-active-tax-columns")).toBe(
      "",
    );
    expect(headerText()).not.toMatch(/HST/);
    expect(container.querySelectorAll('[data-testid="bvd-txn-col-discount"]')[1]?.textContent).toBe(
      "0.00",
    );
    expect(container.querySelectorAll('[data-testid="bvd-txn-col-discount"]')[0]?.textContent).toBe(
      "44.24",
    );
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
    expect(container.querySelector('[data-testid="bvd-txn-col-hst"]')?.textContent).toBe("185.33");
    expect(detail?.querySelector('[data-testid="bvd-txn-tax-hst"]')).toBeNull();
    expect(detail?.textContent).not.toMatch(/Discount/);
    expect(detail?.textContent).not.toMatch(/Retail price/i);
    expect(detail?.textContent).not.toContain("JASPREET");

    act(() => {
      row.click();
    });
    expect(container.querySelector('[data-testid="bvd-txn-detail-1"]')).toBeNull();
  });

  it("G: non-zero discount in main row only", () => {
    renderTable([txn(1, { disc_amt: "5.00" })]);
    expect(container.querySelector('[data-testid="bvd-txn-col-discount"]')?.textContent).toBe("5.00");
    const row = container.querySelector('[data-testid="bvd-txn-row-1"]') as HTMLElement;
    act(() => row.click());
    expect(container.querySelector('[data-testid="bvd-txn-discount"]')).toBeNull();
  });

  it("I: retail and billed in main row; not duplicated in expanded detail", () => {
    renderTable([txn(1, { retail: "3.9890", billed: "3.1067" })]);
    expect(container.querySelector('[data-testid="bvd-txn-col-retail"]')?.textContent).toBe("3.9890");
    expect(container.querySelector('[data-testid="bvd-txn-col-billed"]')?.textContent).toBe("3.1067");
    const row = container.querySelector('[data-testid="bvd-txn-row-1"]') as HTMLElement;
    act(() => row.click());
    const detail = container.querySelector('[data-testid="bvd-txn-detail-1"]');
    expect(detail?.textContent).not.toMatch(/Retail price/i);
    expect(detail?.textContent).not.toMatch(/Billed price/i);
    expect(detail?.textContent).toContain("Pre-tax");
  });

  it("main row shows Fuel for TA", () => {
    renderTable([txn(1)]);
    expect(container.querySelector('[data-testid="bvd-txn-col-product"]')?.textContent).toBe("Fuel");
  });

  function rowIdsInDom(): number[] {
    return Array.from(container.querySelectorAll('[data-testid^="bvd-txn-row-"]')).map((el) => {
      const m = el.getAttribute("data-testid")?.match(/bvd-txn-row-(\d+)/);
      return m ? Number(m[1]) : 0;
    });
  }

  it("default row order matches source transaction order", () => {
    renderTable([txn(3), txn(1), txn(2)]);
    expect(rowIdsInDom()).toEqual([3, 1, 2]);
  });

  it("date sort ascending reorders rows and shows indicator", () => {
    renderTable([
      txn(1, { transaction_date: "2026-07-24 10:00:00" }),
      txn(2, { transaction_date: "2026-07-23 02:17:56" }),
    ]);
    const btn = container.querySelector('[data-testid="bvd-txn-sort-date"]') as HTMLButtonElement;
    act(() => btn.click());
    expect(rowIdsInDom()).toEqual([2, 1]);
    expect(btn.getAttribute("aria-sort")).toBe("ascending");
    expect(btn.textContent).toMatch(/↑/);
  });

  it("clicking same header toggles to descending", () => {
    renderTable([
      txn(1, { transaction_date: "2026-07-24 10:00:00" }),
      txn(2, { transaction_date: "2026-07-23 02:17:56" }),
    ]);
    const btn = container.querySelector('[data-testid="bvd-txn-sort-date"]') as HTMLButtonElement;
    act(() => btn.click());
    act(() => btn.click());
    expect(rowIdsInDom()).toEqual([1, 2]);
    expect(btn.getAttribute("aria-sort")).toBe("descending");
    expect(btn.textContent).toMatch(/↓/);
  });

  it("clicking another header starts ascending on that column", () => {
    renderTable([
      txn(1, { unit_number: "Z9" }),
      txn(2, { unit_number: "001107" }),
    ]);
    const dateBtn = container.querySelector('[data-testid="bvd-txn-sort-date"]') as HTMLButtonElement;
    const unitBtn = container.querySelector('[data-testid="bvd-txn-sort-unit"]') as HTMLButtonElement;
    act(() => dateBtn.click());
    act(() => unitBtn.click());
    expect(rowIdsInDom()).toEqual([2, 1]);
    expect(unitBtn.getAttribute("aria-sort")).toBe("ascending");
    expect(dateBtn.getAttribute("aria-sort")).toBe("none");
  });

  it("unit sort preserves leading-zero identifier display", () => {
    renderTable([
      txn(1, { unit_number: "S1107" }),
      txn(2, { unit_number: "001107" }),
    ]);
    const unitBtn = container.querySelector('[data-testid="bvd-txn-sort-unit"]') as HTMLButtonElement;
    act(() => unitBtn.click());
    expect(rowIdsInDom()).toEqual([2, 1]);
    const units = Array.from(container.querySelectorAll('[data-testid="bvd-txn-col-unit"]')).map(
      (el) => el.textContent,
    );
    expect(units).toEqual(["001107", "S1107"]);
  });

  it("expanded row stays attached after sort", () => {
    renderTable([
      txn(1, { transaction_date: "2026-07-24 10:00:00", auth_code: "AUTH-ONE" }),
      txn(2, { transaction_date: "2026-07-23 02:17:56", auth_code: "AUTH-TWO" }),
    ]);
    const row1 = container.querySelector('[data-testid="bvd-txn-row-1"]') as HTMLElement;
    act(() => row1.click());
    expect(container.querySelector('[data-testid="bvd-txn-detail-1"]')).not.toBeNull();

    const dateBtn = container.querySelector('[data-testid="bvd-txn-sort-date"]') as HTMLButtonElement;
    act(() => dateBtn.click());
    expect(rowIdsInDom()).toEqual([2, 1]);
    const detail = container.querySelector('[data-testid="bvd-txn-detail-1"]');
    expect(detail).not.toBeNull();
    expect(detail?.textContent).toContain("AUTH-ONE");
  });
});
