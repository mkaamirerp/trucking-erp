import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Simulate } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdRow, FuelCanonicalTransaction } from "../../api";
import { getFuelBvdCanonicalTransactions } from "../../api";
import ProcessedStatementWorkspace from "./ProcessedStatementWorkspace";
import { formatProcessedMoneyTotal, sumProcessedChargeFinalAmount } from "./processedStatementMoney";

vi.mock("../../api", () => ({
  getFuelBvdCanonicalTransactions: vi.fn().mockResolvedValue([]),
}));

function txn(id: number, partial: Partial<FuelBvdRow> = {}): FuelBvdRow {
  return {
    id,
    import_id: "838710",
    row_type: "TRANSACTION",
    transaction_date: "2025-12-10 16:00:00",
    unit_number: "1129",
    driver_name: "GURPREET SINGH",
    site_city: "Dunn",
    prov_st: "NC",
    prod: "TA",
    qty: "50.14",
    disc_amt: "44.24",
    hst: "0.00",
    gst: "0.00",
    pst: "0.00",
    qst: "0.00",
    final_amt: "155.77",
    cur: "US",
    auth_code: "A344082616-TA",
    ...partial,
  } as FuelBvdRow;
}

function express(id: number, partial: Partial<FuelBvdRow> = {}): FuelBvdRow {
  return {
    id: 100 + id,
    import_id: "838710",
    row_type: "EXPRESS_TRANSACTION",
    transaction_date: "2025-12-11 10:00:00",
    express_tractor: "1103",
    driver_name: "Nathnel",
    express_code: String(5000000 + id),
    auth_code: `E-express-${id}`,
    payee_raw: "pay",
    amount_cashed: "200.00",
    express_fee: "3.00",
    final_amt: "203.00",
    cur: "US",
    ...partial,
  } as FuelBvdRow;
}

function build838710Rows(): FuelBvdRow[] {
  const purchases: FuelBvdRow[] = [];
  for (let i = 1; i <= 30; i += 1) {
    purchases.push(
      txn(i, {
        final_amt: "237.77",
        unit_number: String(6600 + i),
        driver_name: i === 3 ? "HARPREET" : "DRIVER",
        auth_code: `A347075262-TA-${i}`,
      }),
    );
  }
  purchases.push(txn(31, { final_amt: "237.84", unit_number: "6675", driver_name: "HARPREET" }));
  const expressRows: FuelBvdRow[] = [];
  for (let i = 1; i <= 10; i += 1) {
    expressRows.push(express(i, { final_amt: "152.43", auth_code: `E${i}`, express_code: String(5000000 + i) }));
  }
  expressRows.push(
    express(11, {
      final_amt: "152.48",
      auth_code: "E345296820",
      express_code: "5359948",
      payee_raw: "lumper fee",
      driver_name: "Nathnel",
      express_tractor: "1103",
    }),
  );
  return [
    { id: 0, import_id: "838710", row_type: "HEADER", card_number: "4237111" } as FuelBvdRow,
    { id: 999, import_id: "838710", row_type: "EXPRESS_SUBTOTAL", final_amt: "1676.78" } as FuelBvdRow,
    ...purchases,
    ...expressRows,
  ];
}

describe("ProcessedStatementWorkspace", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function renderWorkspace(rows: FuelBvdRow[], canon: FuelCanonicalTransaction[] = []) {
    vi.mocked(getFuelBvdCanonicalTransactions).mockResolvedValue(canon);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <ProcessedStatementWorkspace
          importId="838710"
          sourceRows={rows}
          cardNumber="4237111"
          invoiceNumber="838710"
          invoiceTotal="9,047.72"
          currency="US"
          fullInvoiceLink={<a href="/detail">Open full invoice</a>}
        />,
      );
    });
    await act(async () => {
      await vi.mocked(getFuelBvdCanonicalTransactions).mock.results.at(-1)?.value;
    });
  }

  it("838710 financial invariant: 42 charges, section totals, invoice total", async () => {
    const rows = build838710Rows();
    const sections = rows.filter((r) => r.row_type === "TRANSACTION" || r.row_type === "EXPRESS_TRANSACTION");
    expect(sections.filter((r) => r.row_type === "TRANSACTION")).toHaveLength(31);
    expect(sections.filter((r) => r.row_type === "EXPRESS_TRANSACTION")).toHaveLength(11);
    expect(formatProcessedMoneyTotal(sumProcessedChargeFinalAmount(sections.filter((r) => r.row_type === "TRANSACTION")))).toBe(
      "7,370.94",
    );
    expect(
      formatProcessedMoneyTotal(sumProcessedChargeFinalAmount(sections.filter((r) => r.row_type === "EXPRESS_TRANSACTION"))),
    ).toBe("1,676.78");

    await renderWorkspace(rows);
    expect(container.querySelector('[data-testid="processed-charge-count"]')?.textContent).toMatch(/42 charges/i);
    const summary = container.querySelector('[data-testid="processed-statement-summary"]');
    expect(summary?.querySelector('[data-testid="processed-card-section-total"]')?.textContent).toContain(
      "7,370.94",
    );
    expect(summary?.querySelector('[data-testid="processed-express-section-total"]')?.textContent).toContain(
      "1,676.78",
    );
    expect(summary?.querySelector('[data-testid="processed-invoice-total"]')?.textContent).toContain("9,047.72");
    expect(container.querySelector('[data-testid="processed-card-section-heading"]')).toBeNull();
    const cardSection = container.querySelector('[aria-label="Fuel and card transactions"]');
    expect(cardSection?.querySelector("thead")).not.toBeNull();
    expect(cardSection?.textContent).not.toMatch(/Fuel \/ Card Transactions\s*\(\d+\)\s*—/);
    expect(container.querySelector('[data-testid="bvd-express-row-111"]')).toBeTruthy();
    expect(container.querySelectorAll('[data-testid^="bvd-txn-row-"]').length).toBe(31);
    expect(container.querySelectorAll('[data-testid^="bvd-express-row-"]').length).toBe(11);
    expect(container.textContent).not.toContain("EXPRESS_SUBTOTAL");
  });

  it("search finds express lumper, auth, and provider reference", async () => {
    const rows = build838710Rows();
    await renderWorkspace(rows);
    const search = container.querySelector("#bvd-statement-search") as HTMLInputElement;
    expect(search).toBeTruthy();

    act(() => {
      Simulate.change(search, { target: { value: "lumper fee" } } as Event & { target: { value: string } });
    });
    expect(container.querySelectorAll('[data-testid^="bvd-express-row-"]').length).toBe(1);

    act(() => {
      Simulate.change(search, { target: { value: "E345296820" } } as Event & { target: { value: string } });
    });
    expect(container.querySelector('[data-testid="bvd-express-col-auth"]')?.textContent).toContain("E345296820");

    act(() => {
      Simulate.change(search, { target: { value: "5359948" } } as Event & { target: { value: string } });
    });
    expect(container.querySelector('[data-testid="bvd-express-col-provider-ref"]')?.textContent).toContain("5359948");

    act(() => {
      Simulate.change(search, { target: { value: "6675" } } as Event & { target: { value: string } });
    });
    expect(container.querySelector('[data-testid="bvd-txn-col-unit"]')?.textContent).toContain("6675");
  });

  it("shows canonical category on express without changing payee_raw", async () => {
    const rows = build838710Rows();
    const canon: FuelCanonicalTransaction[] = [
      {
        provider_transaction_identity: "E345296820",
        classification: "LUMPER",
        provider_reason_raw: "lumper fee",
      } as FuelCanonicalTransaction,
    ];
    await renderWorkspace(rows, canon);
    const row111 = container.querySelector('[data-testid="bvd-express-row-111"]');
    expect(row111?.querySelector('[data-testid="bvd-express-col-reason"]')?.textContent).toBe("lumper fee");
    expect(row111?.querySelector('[data-testid="bvd-express-col-category"]')?.textContent).toBe("LUMPER");
  });

  it("charge sections use native sticky header on real thead cells", async () => {
    const rows = build838710Rows();
    await renderWorkspace(rows);
    expect(container.querySelectorAll(".processed-statement-section--charges").length).toBe(2);
    expect(container.querySelector('[data-testid="bvd-txn-rows-table"]')?.getAttribute("data-processed-native-sticky")).toBe(
      "true",
    );
    expect(container.querySelector('[data-testid="bvd-express-rows-table"]')?.getAttribute("data-processed-native-sticky")).toBe(
      "true",
    );
    expect(container.querySelector(".bvd-txn-rows__header-sticky")).toBeTruthy();
    expect(container.querySelector(".bvd-express-rows__header-sticky")).toBeTruthy();
    expect(container.querySelector(".bvd-processed-charge-table")).toBeNull();
  });

  it("filter meta uses charges wording", async () => {
    const rows = build838710Rows();
    await renderWorkspace(rows);
    expect(container.querySelector('[data-testid="bvd-statement-result-count"]')?.textContent).toBe("42 charges");
  });

  it("838710 card table has no tax columns", async () => {
    const rows = build838710Rows();
    await renderWorkspace(rows);
    const header = container.querySelector('[data-testid="bvd-txn-rows-table"]')?.textContent ?? "";
    expect(header).not.toMatch(/\bHST\b/);
    expect(header).not.toMatch(/\bGST\b/);
    expect(header).toMatch(/Discount/);
  });
});
