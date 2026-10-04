import { describe, expect, it } from "vitest";
import type { FuelBvdRow, FuelCanonicalTransaction } from "../../api";
import {
  countFuelTransactionsByCurrency,
  providerControlVarianceLabel,
} from "./fuelProcessedCurrencyPanel";

describe("fuelProcessedCurrencyPanel", () => {
  it("labels amount under provider control", () => {
    expect(
      providerControlVarianceLabel("USD", "5197.67", [{ currency: "USD", amount: "5197.69" }]),
    ).toBe("0.02 under provider total");
  });

  it("counts canonical transactions by ISO currency", () => {
    const currencyLines = [{ currency: "USD", total_amount: "1050.02", discount_amount: "0.00" }];
    const canonical: FuelCanonicalTransaction[] = [
      {
        id: 1,
        batch_id: 12,
        currency: "USD",
        total_amount: "1050.02",
      },
    ];
    expect(countFuelTransactionsByCurrency(currencyLines, canonical, [])).toEqual({ USD: 1 });
  });

  it("falls back to card rows when canonical list is empty", () => {
    const currencyLines = [{ currency: "USD", total_amount: "10", discount_amount: null }];
    const rows = [{ cur: "US" } as FuelBvdRow];
    expect(countFuelTransactionsByCurrency(currencyLines, [], rows)).toEqual({ USD: 1 });
  });
});
