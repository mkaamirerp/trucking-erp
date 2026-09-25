import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { buildFieldSlotsForPage } from "./bvdFieldSlots";
import { mapPdfJsTextItems, type PdfTextItem } from "./bvdPdfHighlight";

function mockPageDiv(): HTMLElement {
  const page = document.createElement("div");
  page.className = "page";
  const layer = document.createElement("div");
  layer.className = "textLayer";
  page.append(layer);
  page.getBoundingClientRect = () => new DOMRect(0, 0, 800, 1100);
  document.body.append(page);
  return page;
}

function mountSpans(page: HTMLElement, items: PdfTextItem[]) {
  const layer = page.querySelector(".textLayer")!;
  items.forEach((it, i) => {
    const span = document.createElement("span");
    span.textContent = it.str;
    span.getBoundingClientRect = () => new DOMRect(it.x, 1100 - it.y, it.width || 40, it.height || 10);
    layer.append(span);
  });
}

const TXN_HEADER: PdfTextItem[] = mapPdfJsTextItems([
  { str: "Auth Code", transform: [1, 0, 0, 1, 40, 800], width: 50, height: 10 },
  { str: "Driver Name", transform: [1, 0, 0, 1, 120, 800], width: 60, height: 10 },
  { str: "Unit #", transform: [1, 0, 0, 1, 220, 800], width: 30, height: 10 },
  { str: "Final AMT", transform: [1, 0, 0, 1, 500, 800], width: 50, height: 10 },
]);

const TXN_ROW1: PdfTextItem[] = mapPdfJsTextItems([
  { str: "A204040667-TA", transform: [1, 0, 0, 1, 40, 750], width: 80, height: 10 },
  { str: "JASPREET CHOKAR", transform: [1, 0, 0, 1, 120, 750], width: 90, height: 10 },
  { str: "1100", transform: [1, 0, 0, 1, 220, 750], width: 30, height: 10 },
  { str: "1,610.96", transform: [1, 0, 0, 1, 500, 750], width: 40, height: 10 },
]);

describe("bvdFieldSlots identity vs wrong review value", () => {
  it("Unit # slot uses column+auth row when review value is 110O", () => {
    const items = [...TXN_HEADER, ...TXN_ROW1];
    const page = mockPageDiv();
    mountSpans(page, items);
    const row: FuelBvdRow = {
      id: 101,
      import_id: "1",
      row_type: "TRANSACTION",
      source_page: 1,
      source_row_number: 1,
      auth_code: "A204040667-TA",
      unit_number: "110O",
    } as FuelBvdRow;
    const slots = buildFieldSlotsForPage(page, items, [row]);
    const unit = slots.find((s) => s.fieldName === "unit_number");
    expect(unit).toBeDefined();
    expect(unit!.ambiguous).toBe(false);
    expect(unit!.left).toBeGreaterThan(200);
    page.remove();
  });

  it("Grand Total GST slot targets GST column not value search for 9.99 review", () => {
    const gtHeader = mapPdfJsTextItems([
      { str: "PRODUCT", transform: [1, 0, 0, 1, 40, 400], width: 40, height: 10 },
      { str: "QTY", transform: [1, 0, 0, 1, 100, 400], width: 30, height: 10 },
      { str: "GST", transform: [1, 0, 0, 1, 300, 400], width: 30, height: 10 },
      { str: "FINAL AMOUNT", transform: [1, 0, 0, 1, 500, 400], width: 60, height: 10 },
    ]);
    const gtRow = mapPdfJsTextItems([
      { str: "TA", transform: [1, 0, 0, 1, 40, 360], width: 20, height: 10 },
      { str: "1,474.00", transform: [1, 0, 0, 1, 100, 360], width: 50, height: 10 },
      { str: "0.00", transform: [1, 0, 0, 1, 300, 360], width: 30, height: 10 },
      { str: "3,421.01", transform: [1, 0, 0, 1, 500, 360], width: 50, height: 10 },
    ]);
    const items = [...gtHeader, ...gtRow];
    const page = mockPageDiv();
    mountSpans(page, items);
    const row = {
      id: 200,
      import_id: "1",
      row_type: "GRAND_TOTAL",
      source_page: 2,
      source_row_number: 1,
      product: "TA",
      qty: "1,474.00",
      gst: "9.99",
    } as FuelBvdRow;
    const slots = buildFieldSlotsForPage(page, items, [row]);
    const gst = slots.find((s) => s.fieldName === "gst");
    expect(gst).toBeDefined();
    expect(gst!.ambiguous).toBe(false);
    expect(gst!.left).toBeGreaterThan(250);
    page.remove();
  });
});
