import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { FuelBvdCompletedBasic } from "../../api";
import {
  formatFuelActivityAccountCard,
  formatFuelActivityCadTotal,
  formatFuelActivityDueDate,
  formatFuelActivityInvoiceDiscount,
  formatFuelActivityInvoiceTotal,
  formatFuelActivityPeriod,
  formatFuelActivityUsdTotal,
  fuelActivityPaymentLabel,
  fuelActivitySourceMoneyBucket,
} from "./fuelActivityInvoiceDisplay";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../../..");
const golden = JSON.parse(
  readFileSync(join(repoRoot, "tests/fixtures/fuel_bvd_972201_expected.json"), "utf-8"),
) as { rows: Record<string, unknown>[] };

function goldenCompletedBasic(): FuelBvdCompletedBasic {
  const header = golden.rows.find((r) => r.row_type === "HEADER")!;
  const grand = golden.rows.find(
    (r) => r.row_type === "GRAND_TOTAL" && r.row_label === "Grand Total",
  )!;
  return {
    provider: "BVD",
    import_id: "import-972201",
    invoice_number: String(header.invoice_number),
    review_status: "SOURCE_REVIEWED",
    read_only: true,
    card_number: String(header.card_number),
    period_start: String(header.start_date),
    period_end: String(header.end_date),
    due_date: String(header.due_date),
    invoice_disc_amt: "0.00",
    total_amount: "3,421.01",
    currency: String(grand.cur),
    unit_count: 2,
    unit_numbers: ["1100", "1104"],
    categories: [],
    taxes: [],
  };
}

describe("fuelActivityInvoiceDisplay (972201)", () => {
  const row = goldenCompletedBasic();

  it("preserves CN in source currency (dashboard maps to CAD column only)", () => {
    expect(row.currency).toBe("CN");
    expect(fuelActivitySourceMoneyBucket(row.currency)).toBe("cad");
    expect(formatFuelActivityCadTotal(row)).toBe("3,421.01");
    expect(formatFuelActivityUsdTotal(row)).toBe("—");
    expect(formatFuelActivityInvoiceTotal(row)).toBe("3,421.01 CN");
  });

  it("formats period from header start/end (same month)", () => {
    expect(formatFuelActivityPeriod(row.period_start, row.period_end)).toBe("Jul 22–28");
  });

  it("formats due date without timestamp", () => {
    expect(formatFuelActivityDueDate(row.due_date)).toBe("Jul 30, 2026");
  });

  it("shows payment as not tracked", () => {
    expect(fuelActivityPaymentLabel(row)).toBe("Not tracked");
  });

  it("shows grand-total discount zero", () => {
    expect(formatFuelActivityInvoiceDiscount(row)).toBe("0.00");
  });

  it("USD bucket separate — no FX", () => {
    const usdRow: FuelBvdCompletedBasic = {
      ...row,
      currency: "USD",
      total_amount: "2,430.70",
    };
    expect(formatFuelActivityUsdTotal(usdRow)).toBe("2,430.70");
    expect(formatFuelActivityCadTotal(usdRow)).toBe("—");
  });

  it("missing bucket amount is em dash not zero", () => {
    expect(formatFuelActivityUsdTotal(row)).toBe("—");
  });
});

describe("fuelActivitySourceMoneyBucket", () => {
  it("maps provider codes to display buckets only", () => {
    expect(fuelActivitySourceMoneyBucket("US")).toBe("usd");
    expect(fuelActivitySourceMoneyBucket("USD")).toBe("usd");
    expect(fuelActivitySourceMoneyBucket("CN")).toBe("cad");
    expect(fuelActivitySourceMoneyBucket("CAD")).toBe("cad");
    expect(fuelActivitySourceMoneyBucket("EUR")).toBeNull();
    expect(fuelActivitySourceMoneyBucket(null)).toBeNull();
  });
});

describe("838710 US currency display", () => {
  const usRow: FuelBvdCompletedBasic = {
    ...goldenCompletedBasic(),
    import_id: "imp-838710",
    invoice_number: "838710",
    currency: "US",
    total_amount: "9,047.72",
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
    card_number: "4237160",
  };

  it("fills USD column and preserves provider US on invoice total", () => {
    expect(formatFuelActivityCadTotal(usRow)).toBe("—");
    expect(formatFuelActivityUsdTotal(usRow)).toBe("9,047.72");
    expect(formatFuelActivityInvoiceTotal(usRow)).toBe("9,047.72 US");
  });

  it("shows multi-card summary not header card alone", () => {
    expect(formatFuelActivityAccountCard(usRow)).toBe("7 cards");
    expect(formatFuelActivityAccountCard(usRow)).not.toBe("4237160");
  });
});

describe("formatFuelActivityAccountCard", () => {
  const base = goldenCompletedBasic();

  it("one card shows exact number", () => {
    expect(
      formatFuelActivityAccountCard({
        ...base,
        purchase_card_count: 1,
        purchase_card_numbers: ["4237111"],
      }),
    ).toBe("4237111");
  });

  it("seven cards shows count label", () => {
    expect(
      formatFuelActivityAccountCard({
        ...base,
        purchase_card_count: 7,
        purchase_card_numbers: ["4236501", "4236576"],
      }),
    ).toBe("7 cards");
  });

  it("zero cards shows em dash", () => {
    expect(
      formatFuelActivityAccountCard({
        ...base,
        purchase_card_count: 0,
        purchase_card_numbers: [],
      }),
    ).toBe("—");
  });
});
