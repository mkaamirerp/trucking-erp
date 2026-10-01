import { describe, expect, it } from "vitest";
import { processedChargeHeaderLineCount } from "./processedChargeHeaderLabels";

describe("processedChargeHeaderLabels", () => {
  it("uses two lines for multi-word price and driver headers", () => {
    expect(processedChargeHeaderLineCount("Retail price")).toBe(2);
    expect(processedChargeHeaderLineCount("Billed price")).toBe(2);
    expect(processedChargeHeaderLineCount("Final amount")).toBe(2);
    expect(processedChargeHeaderLineCount("Source driver")).toBe(2);
    expect(processedChargeHeaderLineCount("Date / Time")).toBe(2);
  });

  it("keeps single-word headers on one line", () => {
    expect(processedChargeHeaderLineCount("Product")).toBe(1);
    expect(processedChargeHeaderLineCount("Discount")).toBe(1);
    expect(processedChargeHeaderLineCount("HST")).toBe(1);
  });
});
