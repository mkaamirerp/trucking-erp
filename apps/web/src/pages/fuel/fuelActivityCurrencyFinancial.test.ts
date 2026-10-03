import { describe, expect, it } from "vitest";
import type { FuelProcessedSummary } from "../../api";
import {
  formatFuelActivityInvoiceTotalFromCurrencySummaries,
  formatFuelActivityStatementCurrencyLine,
  processedSectionSummaryAmount,
  resolveFuelCurrencyFinancialSummaries,
} from "./fuelActivityCurrencyFinancial";

describe("fuelActivityCurrencyFinancial", () => {
  const mixed: Pick<FuelProcessedSummary, "currency_financial_summaries" | "currency_totals"> = {
    currency_financial_summaries: [
      { currency: "CAD", total_amount: "1263.8500", discount_amount: "0.0000" },
      { currency: "USD", total_amount: "5197.6700", discount_amount: "145.1200" },
    ],
    currency_totals: [],
  };

  it("uses canonical financial summaries when present", () => {
    const lines = resolveFuelCurrencyFinancialSummaries(mixed);
    expect(lines).toHaveLength(2);
    expect(lines[0].currency).toBe("CAD");
    expect(lines[1].currency).toBe("USD");
  });

  it("formats one currency line with discount and total", () => {
    expect(formatFuelActivityStatementCurrencyLine(mixed.currency_financial_summaries![1])).toBe(
      "USD · Discount 145.1200 · Total 5197.6700 USD",
    );
  });

  it("formats invoice total for multiple currencies without mixing", () => {
    expect(formatFuelActivityInvoiceTotalFromCurrencySummaries(resolveFuelCurrencyFinancialSummaries(mixed))).toBe(
      "1263.8500 CAD · 5197.6700 USD",
    );
  });

  it("shows only one line when one currency exists", () => {
    const single = resolveFuelCurrencyFinancialSummaries({
      currency_financial_summaries: [
        { currency: "USD", total_amount: "100.00", discount_amount: "5.00" },
      ],
      currency_totals: [],
    });
    expect(single).toHaveLength(1);
    expect(formatFuelActivityInvoiceTotalFromCurrencySummaries(single)).toBe("100.00 USD");
  });

  it("falls back to currency_totals with unknown discount when summaries missing", () => {
    const lines = resolveFuelCurrencyFinancialSummaries({
      currency_financial_summaries: [],
      currency_totals: [{ currency: "EUR", amount: "99.50" }],
    });
    expect(lines).toEqual([{ currency: "EUR", total_amount: "99.50", discount_amount: null }]);
  });

  it("formats EUR single-currency line", () => {
    const line = {
      currency: "EUR",
      total_amount: "8421.55",
      discount_amount: "125.20",
    };
    expect(formatFuelActivityStatementCurrencyLine(line)).toBe(
      "EUR · Discount 125.20 · Total 8421.55 EUR",
    );
    expect(formatFuelActivityInvoiceTotalFromCurrencySummaries([line])).toBe("8421.55 EUR");
  });

  it("renders three currency lines without combining amounts", () => {
    const lines = resolveFuelCurrencyFinancialSummaries({
      currency_financial_summaries: [
        { currency: "AUD", total_amount: "1.00", discount_amount: "0.10" },
        { currency: "MXN", total_amount: "2.00", discount_amount: "0.20" },
        { currency: "NZD", total_amount: "3.00", discount_amount: "0.30" },
      ],
      currency_totals: [],
    });
    expect(lines).toHaveLength(3);
    expect(formatFuelActivityInvoiceTotalFromCurrencySummaries(lines)).toBe(
      "1.00 AUD · 2.00 MXN · 3.00 NZD",
    );
  });

  it("omits mixed-currency section amount instead of summing unlike currencies", () => {
    const lines = resolveFuelCurrencyFinancialSummaries({
      currency_financial_summaries: [
        { currency: "CAD", total_amount: "1263.85", discount_amount: "0" },
        { currency: "USD", total_amount: "5197.67", discount_amount: "1" },
      ],
      currency_totals: [],
    });
    expect(processedSectionSummaryAmount(lines, 6461.52, ["CAD", "USD"])).toBeNull();
  });

  it("shows single-currency section amount from summaries", () => {
    const lines = resolveFuelCurrencyFinancialSummaries({
      currency_financial_summaries: [{ currency: "EUR", total_amount: "8421.55", discount_amount: "0" }],
      currency_totals: [],
    });
    expect(processedSectionSummaryAmount(lines, 999, [])).toBe("8421.55 EUR");
  });

  it("shows em dash for unknown discount and 0.00 for known zero", () => {
    expect(
      formatFuelActivityStatementCurrencyLine({
        currency: "GBP",
        total_amount: "10",
        discount_amount: null,
      }),
    ).toContain("Discount —");
    expect(
      formatFuelActivityStatementCurrencyLine({
        currency: "CAD",
        total_amount: "1263.85",
        discount_amount: "0.00",
      }),
    ).toContain("Discount 0.00");
  });
});
