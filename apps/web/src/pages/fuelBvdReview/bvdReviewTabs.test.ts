import { describe, expect, it } from "vitest";
import { defaultTabForRowType, rowsForTab } from "./bvdReviewTabs";
import type { FuelBvdRow } from "../../api";

const row = (partial: Partial<FuelBvdRow> & Pick<FuelBvdRow, "id" | "row_type">): FuelBvdRow =>
  ({
    import_id: "x",
    source_row_number: 1,
    ...partial,
  }) as FuelBvdRow;

describe("bvdReviewTabs", () => {
  const rows: FuelBvdRow[] = [
    row({ id: 1, row_type: "HEADER", invoice_number: "972201" }),
    row({ id: 2, row_type: "TRANSACTION", auth_code: "A204040667-TA" }),
    row({ id: 3, row_type: "TRANSACTION_SUBTOTAL", row_label: "SUBTOTAL" }),
    row({ id: 4, row_type: "PAGE1_SUMMARY", row_label: "Fuel Total" }),
    row({ id: 5, row_type: "GRAND_TOTAL", final_amount: "3,421.01" }),
    row({ id: 6, row_type: "LEGEND", legend_code: "L" }),
  ];

  it("filters rows per tab", () => {
    expect(rowsForTab(rows, "HEADER")).toHaveLength(1);
    expect(rowsForTab(rows, "TRANSACTIONS")).toHaveLength(1);
    expect(rowsForTab(rows, "CONTROLS")).toHaveLength(2);
    expect(rowsForTab(rows, "GRAND_TOTAL")).toHaveLength(1);
    expect(rowsForTab(rows, "LEGEND")).toHaveLength(1);
  });

  it("maps row types to tabs", () => {
    expect(defaultTabForRowType("TRANSACTION")).toBe("TRANSACTIONS");
    expect(defaultTabForRowType("PAGE1_SUMMARY")).toBe("CONTROLS");
  });
});
