import { describe, expect, it } from "vitest";
import { getTextLayerSpanElements, resolveDomHighlightRect } from "./bvdPdfDomHighlight";
import { mapPdfJsTextItems, type HighlightLookupContext, type PdfTextItem } from "./bvdPdfHighlight";

function mockPageWithTextLayer(items: PdfTextItem[]) {
  const pageDiv = document.createElement("div");
  pageDiv.className = "page";
  const layer = document.createElement("div");
  layer.className = "textLayer";
  pageDiv.append(layer);
  items.forEach((item, i) => {
    const span = document.createElement("span");
    span.textContent = item.str;
    const top = 100 + i * 20;
    span.getBoundingClientRect = () =>
      new DOMRect(50 + item.x, top, item.width || 40, item.height || 12);
    layer.append(span);
  });
  pageDiv.getBoundingClientRect = () => new DOMRect(0, 0, 600, 800);
  document.body.append(pageDiv);
  return pageDiv;
}

describe("bvdPdfDomHighlight", () => {
  it("maps semantic item indices to display rect relative to page div", () => {
    const items: PdfTextItem[] = mapPdfJsTextItems([
      { str: "3,421.01", transform: [1, 0, 0, 1, 400, 500], width: 60, height: 10 },
    ]);
    const pageDiv = mockPageWithTextLayer(items);
    const ctx: HighlightLookupContext = {
      page: 2,
      field: "final_amount",
      label: "Final amount",
      value: "3,421.01",
      rowType: "GRAND_TOTAL",
      sourceRowNumber: 1,
      selectionKey: "1:final_amount",
      anchorField: "product",
      anchorValue: "TA",
      rowQtyHint: "1,474.00",
    };
    const { rect, ambiguous } = resolveDomHighlightRect(pageDiv, items, ctx);
    expect(ambiguous).toBe(false);
    expect(rect).not.toBeNull();
    expect(rect!.width).toBeGreaterThan(0);
    expect(getTextLayerSpanElements(pageDiv)).toHaveLength(1);
    pageDiv.remove();
  });
});
