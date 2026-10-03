import { describe, expect, it } from "vitest";
import { providerControlVarianceLabel } from "./fuelProcessedCurrencyPanel";

describe("fuelProcessedCurrencyPanel", () => {
  it("labels amount under provider control", () => {
    expect(
      providerControlVarianceLabel("USD", "5197.67", [{ currency: "USD", amount: "5197.69" }]),
    ).toBe("0.02 under provider total");
  });
});
