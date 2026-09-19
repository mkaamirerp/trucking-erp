import { describe, expect, it } from "vitest";

/** Mirrors backend authority boundary for Fuel source review UI. */
const FORBIDDEN_REVIEW_FIELDS = new Set([
  "truck_id",
  "driver_id",
  "owner_operator_payee_id",
  "owner_operator_charge_amount",
  "financial_responsibility",
  "settlement_ref",
  "provider_raw",
  "gate_status",
]);

function buildCorrections(
  editableFields: string[],
  original: Record<string, unknown>,
  draft: Record<string, string>,
  reason: string,
): Array<{ field: string; reviewed_value: unknown; reason: string }> {
  const out: Array<{ field: string; reviewed_value: unknown; reason: string }> = [];
  for (const field of editableFields) {
    if (FORBIDDEN_REVIEW_FIELDS.has(field)) continue;
    const originalStr =
      original[field] === null || original[field] === undefined ? "" : String(original[field]);
    const nextStr = draft[field] ?? "";
    if (nextStr === originalStr) continue;
    if (!reason.trim()) throw new Error("Correction reason is required when changing a value");
    out.push({ field, reviewed_value: nextStr === "" ? null : nextStr, reason: reason.trim() });
  }
  return out;
}

describe("Fuel review correction builder", () => {
  it("requires reason when a value changes", () => {
    expect(() =>
      buildCorrections(["total_amount"], { total_amount: "10.00" }, { total_amount: "11.00" }, ""),
    ).toThrow(/reason/i);
  });

  it("emits decimal string corrections and skips unchanged", () => {
    const corrections = buildCorrections(
      ["total_amount", "city"],
      { total_amount: "10.00", city: "TROY" },
      { total_amount: "10.50", city: "TROY" },
      "Amount OCR fix",
    );
    expect(corrections).toEqual([
      { field: "total_amount", reviewed_value: "10.50", reason: "Amount OCR fix" },
    ]);
  });

  it("never proposes forbidden authority fields", () => {
    const corrections = buildCorrections(
      ["truck_id", "total_amount"],
      { truck_id: "1", total_amount: "1.00" },
      { truck_id: "2", total_amount: "1.00" },
      "should not apply truck",
    );
    expect(corrections).toEqual([]);
  });

  it("is provider-neutral (same path for BVD and Nationwide field bags)", () => {
    const bvd = buildCorrections(
      ["currency_raw"],
      { currency_raw: "CN" },
      { currency_raw: "CAD" },
      "normalize label",
    );
    const nw = buildCorrections(
      ["currency_raw"],
      { currency_raw: "USD" },
      { currency_raw: "USD" },
      "noop",
    );
    expect(bvd[0].field).toBe("currency_raw");
    expect(nw).toEqual([]);
  });
});
