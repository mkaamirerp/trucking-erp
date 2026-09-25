import { describe, expect, it } from "vitest";
import { mapPdfJsTextItems, pickGrandTotalProductAnchorIndex, resolveSemanticTextMatch } from "./bvdPdfHighlight";

const PAGE2_TA_ROW = mapPdfJsTextItems([
  { str: "TA", transform: [1, 0, 0, 1, 40, 400], width: 12, height: 10 },
  { str: "1,474.00", transform: [1, 0, 0, 1, 80, 400], width: 50, height: 10 },
  { str: "0.00", transform: [1, 0, 0, 1, 200, 400], width: 24, height: 10 },
  { str: "TA", transform: [1, 0, 0, 1, 40, 200], width: 12, height: 10 },
  { str: "Legend", transform: [1, 0, 0, 1, 40, 100], width: 40, height: 10 },
]);

describe("pickGrandTotalProductAnchorIndex", () => {
  it("resolves TA fuel row using qty hint when TA appears twice", () => {
    const idx = pickGrandTotalProductAnchorIndex(PAGE2_TA_ROW, "TA", "1,474.00");
    expect(idx).toBe(0);
  });

  it("returns null when multiple TA rows lack qty hint", () => {
    const idx = pickGrandTotalProductAnchorIndex(PAGE2_TA_ROW, "TA");
    expect(idx).toBeNull();
  });

  it("marks GST 0.00 ambiguous when multiple TA anchors lack qty hint", () => {
    const items = mapPdfJsTextItems([
      { str: "TA", transform: [1, 0, 0, 1, 40, 400], width: 12, height: 10 },
      { str: "0.00", transform: [1, 0, 0, 1, 200, 400], width: 24, height: 10 },
      { str: "TA", transform: [1, 0, 0, 1, 40, 200], width: 12, height: 10 },
      { str: "0.00", transform: [1, 0, 0, 1, 200, 200], width: 24, height: 10 },
    ]);
    const match = resolveSemanticTextMatch(items, {
      page: 2,
      field: "gst",
      label: "GST",
      value: "0.00",
      rowType: "GRAND_TOTAL",
      sourceRowNumber: 1,
      selectionKey: "x:gst",
      anchorField: "product",
      anchorValue: "TA",
    });
    expect(match?.ambiguous).toBe(true);
  });
});
