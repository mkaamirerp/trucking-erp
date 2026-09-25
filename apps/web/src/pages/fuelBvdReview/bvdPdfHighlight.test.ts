import { describe, expect, it } from "vitest";
import {
  findValueMatches,
  mapPdfJsTextItems,
  resolveHighlightOnPage,
  type PdfTextItem,
} from "./bvdPdfHighlight";

/** Minimal text-layer mock: two transaction rows with duplicate GST 0.00 */
const PAGE_ITEMS: PdfTextItem[] = mapPdfJsTextItems([
  { str: "A204040667-TA", transform: [1, 0, 0, 1, 40, 700], width: 80, height: 10 },
  { str: "1100", transform: [1, 0, 0, 1, 200, 700], width: 30, height: 10 },
  { str: "0.00", transform: [1, 0, 0, 1, 400, 700], width: 24, height: 10 },
  { str: "A208448597-TA", transform: [1, 0, 0, 1, 40, 650], width: 80, height: 10 },
  { str: "1104", transform: [1, 0, 0, 1, 200, 650], width: 30, height: 10 },
  { str: "0.00", transform: [1, 0, 0, 1, 400, 650], width: 24, height: 10 },
]);

describe("bvdPdfHighlight", () => {
  it("finds unique unit number match", () => {
    const matches = findValueMatches(PAGE_ITEMS, "1100");
    expect(matches).toHaveLength(1);
  });

  it("disambiguates duplicate 0.00 using auth_code anchor row 1", () => {
    const rect = resolveHighlightOnPage(PAGE_ITEMS, {
      page: 1,
      field: "gst",
      label: "GST",
      value: "0.00",
      rowType: "TRANSACTION",
      sourceRowNumber: 2,
      selectionKey: "2:gst",
      anchorField: "auth_code",
      anchorValue: "A204040667-TA",
    });
    expect(rect).not.toBeNull();
    expect(rect!.y).toBeCloseTo(690, 0);
  });

  it("disambiguates duplicate 0.00 for second transaction", () => {
    const rect = resolveHighlightOnPage(PAGE_ITEMS, {
      page: 1,
      field: "gst",
      label: "GST",
      value: "0.00",
      rowType: "TRANSACTION",
      sourceRowNumber: 4,
      selectionKey: "4:gst",
      anchorField: "auth_code",
      anchorValue: "A208448597-TA",
    });
    expect(rect).not.toBeNull();
    expect(rect!.y).toBeCloseTo(640, 0);
  });

  it("marks ambiguous when anchor missing for duplicate values", () => {
    const rect = resolveHighlightOnPage(PAGE_ITEMS, {
      page: 1,
      field: "gst",
      label: "GST",
      value: "0.00",
      rowType: "TRANSACTION",
      sourceRowNumber: 2,
      selectionKey: "2:gst",
    });
    expect(rect?.ambiguous).toBe(true);
  });
});
