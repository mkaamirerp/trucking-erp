import { describe, expect, it } from "vitest";
import { formatNationwideCell, nationwideControlColumns } from "./nationwideCellFormat";

describe("formatNationwideCell", () => {
  it("maps OON dash artifacts to em dash", () => {
    expect(formatNationwideCell("oon_fees", "-$")).toBe("—");
    expect(formatNationwideCell("oon_fees", "-")).toBe("—");
    expect(formatNationwideCell("oon_fees", "")).toBe("—");
  });

  it("shows explicit zero as 0.00 for OON fees", () => {
    expect(formatNationwideCell("oon_fees", "0")).toBe("0.00");
    expect(formatNationwideCell("oon_fees", "0.00")).toBe("0.00");
    expect(formatNationwideCell("oon_fees", "$0.00")).toBe("0.00");
  });

  it("preserves nonzero OON amounts", () => {
    expect(formatNationwideCell("oon_fees", "12.34")).toBe("12.34");
    expect(formatNationwideCell("oon_fees", "$5.00")).toBe("$5.00");
  });
});

describe("nationwideControlColumns", () => {
  it("separates type, label, and amount", () => {
    const cols = nationwideControlColumns({
      id: 1,
      import_id: "x",
      row_type: "CONTROL",
      control_type: "CURRENCY_TOTAL",
      row_label: "USD billing total",
      declared_amount: "$5,197.69",
    });
    expect(cols).toEqual({
      type: "CURRENCY_TOTAL",
      label: "USD billing total",
      amount: "$5,197.69",
    });
  });

  it("shows card identity and provider USD total from staged raw line", () => {
    const cols = nationwideControlColumns({
      id: 2,
      import_id: "x",
      row_type: "CONTROL",
      control_type: "CARD_TOTAL",
      row_label: "CARD_TOTAL",
      card_number: "XXXXX07588",
      control_line_raw: "XXXXX07588 Total 154.27 $722.75 $34.56 $0.00",
    });
    expect(cols.type).toBe("CARD_TOTAL");
    expect(cols.label).toBe("XXXXX07588 · USD");
    expect(cols.amount).toBe("722.75");
  });

  it("shows CAD card total with GST from provider raw line", () => {
    const cols = nationwideControlColumns({
      id: 3,
      import_id: "x",
      row_type: "CONTROL",
      control_type: "CARD_TOTAL",
      row_label: "CARD_TOTAL",
      card_number: "XXXXX87195",
      control_line_raw: "XXXXX87195 Total GST $145.4 QST $0 674.17 $1,263.85 $0.00 $0.00",
    });
    expect(cols.label).toBe("XXXXX87195 · CAD");
    expect(cols.amount).toBe("1263.85 · GST 145.40");
  });
});
