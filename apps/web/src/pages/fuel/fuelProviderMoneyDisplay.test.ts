import { describe, expect, it } from "vitest";
import {
  formatDualCurrencyInvoiceTotalLabel,
  formatProviderMoneyAmount,
} from "./fuelProviderMoneyDisplay";

describe("fuelProviderMoneyDisplay", () => {
  it("maps blank provider money to 0.00 when configured", () => {
    expect(formatProviderMoneyAmount("", { emptyAsZero: true })).toBe("0.00");
    expect(formatProviderMoneyAmount("—", { emptyAsZero: true })).toBe("0.00");
    expect(formatProviderMoneyAmount(null, { emptyAsZero: true })).toBe("0.00");
  });

  it("keeps em dash for unknown money when not zero-default", () => {
    expect(formatProviderMoneyAmount("")).toBe("—");
  });

  it("joins dual-currency invoice labels", () => {
    expect(formatDualCurrencyInvoiceTotalLabel("1.00", "2.00")).toBe("1.00 CAD · 2.00 USD");
    expect(formatDualCurrencyInvoiceTotalLabel("—", "2.00")).toBe("2.00 USD");
  });
});
