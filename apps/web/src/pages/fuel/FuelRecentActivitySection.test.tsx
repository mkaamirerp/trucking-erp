import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdCompletedBasic, FuelBvdRow } from "../../api";
import { OPS } from "../../routes";
import FuelRecentActivitySection from "./FuelRecentActivitySection";

const apiMocks = vi.hoisted(() => ({
  getFuelBvdImportRows: vi.fn(),
}));

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return { ...actual, getFuelBvdImportRows: apiMocks.getFuelBvdImportRows };
});

const completed = (importId: string, invoice: string): FuelBvdCompletedBasic => ({
  provider: "BVD",
  import_id: importId,
  invoice_number: invoice,
  review_status: "SOURCE_REVIEWED",
  read_only: true,
  processed_at: "2026-09-27T12:00:00Z",
  unit_count: 2,
  unit_numbers: ["1100"],
  total_amount: "3,421.01",
  currency: "CN",
  categories: [],
  taxes: [],
  card_number: "4237111",
  purchase_card_count: 1,
  purchase_card_numbers: ["4237111"],
  due_date: "2026-07-30 23:59:59",
  invoice_disc_amt: "0.00",
});

function txnRow(id: number): FuelBvdRow {
  return {
    id,
    import_id: "imp-a",
    row_type: "TRANSACTION",
    transaction_date: "2026-07-23 02:17:56",
    unit_number: "1100",
    driver_name: "JASPREET CHOKAR",
    site_city: "BOWMANVILLE",
    site_name: "BOWMANVILLE",
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
  } as FuelBvdRow;
}

describe("FuelRecentActivitySection", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    apiMocks.getFuelBvdImportRows.mockReset();
  });

  async function renderSection(activity: FuelBvdCompletedBasic[]) {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter>
          <FuelRecentActivitySection activity={activity} loading={false} />
        </MemoryRouter>,
      );
    });
  }

  it("C: shows invoice summaries only before expand", async () => {
    await renderSection([completed("imp-a", "972201")]);
    expect(container.querySelector('[data-testid="fuel-activity-txn-panel-imp-a"]')).toBeNull();
    expect(container.querySelector('[data-testid^="bvd-txn-row-"]')).toBeNull();
    expect(container.textContent).toContain("972201");
    expect(container.querySelector('[data-testid="fuel-activity-card-imp-a"]')?.textContent).toBe(
      "4237111",
    );
  });

  it("multi-card invoice shows card count not header card", async () => {
    await renderSection([
      {
        ...completed("imp-mc", "838710"),
        invoice_number: "838710",
        card_number: "4237160",
        purchase_card_count: 7,
        purchase_card_numbers: [
          "4236501",
          "4236576",
          "4236675",
          "4236980",
          "4237061",
          "4237160",
          "4237186",
        ],
        currency: "US",
        total_amount: "9,047.72",
      },
    ]);
    const cardCell = container.querySelector('[data-testid="fuel-activity-card-imp-mc"]');
    expect(cardCell?.textContent).toBe("7 cards");
    expect(cardCell?.textContent).not.toContain("4237160");
  });

  it("overlay Open handler fires without route navigation", async () => {
    const onOpen = vi.fn();
    await renderSection([completed("imp-a", "972201")]);
    await act(async () => {
      root.render(
        <MemoryRouter>
          <FuelRecentActivitySection activity={[completed("imp-a", "972201")]} loading={false} onOpenProcessed={onOpen} />
        </MemoryRouter>,
      );
    });
    const openBtn = container.querySelector('[data-testid="fuel-activity-open-imp-a"]') as HTMLButtonElement;
    await act(async () => {
      openBtn.click();
    });
    expect(onOpen).toHaveBeenCalledWith("imp-a");
    expect(openBtn.tagName).toBe("BUTTON");
  });

  it("D–J: lazy load, compact rows, txn expand, single invoice expand, full invoice link", async () => {
    apiMocks.getFuelBvdImportRows.mockImplementation(async (id: string) => {
      if (id === "imp-a") {
        return [
          { id: 1, import_id: id, row_type: "HEADER", card_number: "4237111" } as FuelBvdRow,
          txnRow(2),
        ];
      }
      return [{ id: 10, import_id: id, row_type: "HEADER" } as FuelBvdRow, { ...txnRow(11), id: 11 } as FuelBvdRow];
    });

    await renderSection([completed("imp-a", "972201"), completed("imp-b", "972202")]);

    const rowA = container.querySelector('[data-testid="fuel-activity-invoice-imp-a"]') as HTMLElement;
    await act(async () => {
      rowA.querySelector("button")?.click();
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(apiMocks.getFuelBvdImportRows).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFuelBvdImportRows).toHaveBeenCalledWith("imp-a");
    expect(container.querySelector('[data-testid="fuel-activity-txn-panel-imp-a"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="bvd-statement-filters"]')).toBeTruthy();
    expect(container.textContent).toContain("Search this statement");
    expect(container.querySelector('[data-testid="bvd-txn-row-2"]')).toBeTruthy();

    const fullLink = container.querySelector('[data-testid="fuel-activity-full-invoice-imp-a"]') as HTMLAnchorElement;
    expect(fullLink.getAttribute("href")).toBe(OPS.FUEL_BVD_DETAIL("imp-a"));

    const openLink = container.querySelector('[data-testid="fuel-activity-open-imp-a"]') as HTMLAnchorElement;
    expect(openLink.getAttribute("href")).toBe(OPS.FUEL_BVD_DETAIL("imp-a"));

    const txnRowEl = container.querySelector('[data-testid="bvd-txn-row-2"]') as HTMLElement;
    await act(async () => {
      txnRowEl.click();
    });
    const detail = container.querySelector('[data-testid="bvd-txn-detail-2"]');
    expect(detail?.textContent).toMatch(/HST/);
    expect(detail?.querySelector('[data-testid="bvd-txn-tax-gst"]')).toBeNull();
    expect(detail?.textContent).not.toMatch(/Discount/);

    const rowB = container.querySelector('[data-testid="fuel-activity-invoice-imp-b"]') as HTMLElement;
    await act(async () => {
      rowB.querySelector("button")?.click();
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(container.querySelector('[data-testid="fuel-activity-invoice-imp-a"]')?.getAttribute("data-expanded")).toBe(
      "false",
    );
    expect(container.querySelector('[data-testid="fuel-activity-txn-panel-imp-b"]')).toBeTruthy();
    expect(apiMocks.getFuelBvdImportRows).toHaveBeenCalledWith("imp-b");
  });
});
