import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { BVD_HEADER_FIELDS } from "../fuelBvdReviewLabels";
import { buildFieldSlotsForPage } from "./bvdFieldSlots";
import { getReviewFieldState } from "./bvdFieldCapture";
import { buildReviewLogicalRows, buildReviewLogicalRowsMerged } from "./bvdReviewLines";
import { discoverUnmappedSourceFields } from "./bvdUnmappedSource";
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
  items.forEach((it) => {
    const span = document.createElement("span");
    span.textContent = it.str;
    span.getBoundingClientRect = () => new DOMRect(it.x, 1100 - it.y, it.width || 40, it.height || 10);
    layer.append(span);
  });
}

function txnRow(id: number, unit: string, auth: string, y: number): FuelBvdRow {
  return {
    id,
    import_id: "dyn",
    row_type: "TRANSACTION",
    source_page: 1,
    source_row_number: id,
    auth_code: auth,
    unit_number: unit,
  } as FuelBvdRow;
}

const TXN_HEADER: PdfTextItem[] = mapPdfJsTextItems([
  { str: "Auth Code", transform: [1, 0, 0, 1, 40, 700], width: 50, height: 10 },
  { str: "Unit #", transform: [1, 0, 0, 1, 220, 700], width: 30, height: 10 },
  { str: "Final AMT", transform: [1, 0, 0, 1, 500, 700], width: 50, height: 10 },
]);

describe("BVD mirror dynamic layout (not fixture-shaped)", () => {
  it("A: five transaction rows produce five shared logical transaction line numbers", () => {
    const header = { id: 1, import_id: "dyn", row_type: "HEADER", source_page: 1 } as FuelBvdRow;
    const txns = [1, 2, 3, 4, 5].map((n) => txnRow(10 + n, `U-${n}`, `AUTH-${n}-TA`, 650 - n * 20));
    const lines = buildReviewLogicalRows([header, ...txns]);
    const txnLines = lines.filter((l) => l.rowType === "TRANSACTION");
    expect(txnLines).toHaveLength(5);
    expect(txnLines.map((l) => l.reviewLineNumber)).toEqual([
      BVD_HEADER_FIELDS.length + 1,
      BVD_HEADER_FIELDS.length + 2,
      BVD_HEADER_FIELDS.length + 3,
      BVD_HEADER_FIELDS.length + 4,
      BVD_HEADER_FIELDS.length + 5,
    ]);
  });

  it("B: unit column slots follow arbitrary unit numbers (not 1100/1104)", () => {
    const items = [
      ...TXN_HEADER,
      ...mapPdfJsTextItems([
        { str: "AUTH-9-TA", transform: [1, 0, 0, 1, 40, 620], width: 80, height: 10 },
        { str: "UNIT-999", transform: [1, 0, 0, 1, 220, 620], width: 40, height: 10 },
      ]),
    ];
    const page = mockPageDiv();
    mountSpans(page, items);
    const row = txnRow(99, "UNIT-999", "AUTH-9-TA", 620);
    const slots = buildFieldSlotsForPage(page, items, [row]);
    const unit = slots.find((s) => s.fieldName === "unit_number");
    expect(unit?.ambiguous).toBe(false);
    expect(unit!.left).toBeGreaterThan(200);
    page.remove();
  });

  it("C: extra subtotal row becomes its own logical review line", () => {
    const rows: FuelBvdRow[] = [
      { id: 1, import_id: "x", row_type: "HEADER", source_page: 1 } as FuelBvdRow,
      txnRow(2, "1", "A-TA", 600),
      {
        id: 3,
        import_id: "x",
        row_type: "TRANSACTION_SUBTOTAL",
        source_page: 1,
        source_row_number: 99,
        row_label: "Control subtotal",
      } as FuelBvdRow,
    ];
    const lines = buildReviewLogicalRows(rows);
    expect(lines.some((l) => l.rowType === "TRANSACTION_SUBTOTAL" && l.label.includes("Control"))).toBe(true);
  });

  it("D: unknown label/value pair is surfaced as unmapped source field", () => {
    const items = [
      ...TXN_HEADER,
      ...mapPdfJsTextItems([
        { str: "New Fee Type:", transform: [1, 0, 0, 1, 40, 900], width: 80, height: 10 },
        { str: "ABC", transform: [1, 0, 0, 1, 200, 900], width: 40, height: 10 },
      ]),
    ];
    const page = mockPageDiv();
    mountSpans(page, items);
    const { unmapped } = discoverUnmappedSourceFields(page, items, 1, []);
    expect(unmapped.some((u) => u.label.toLowerCase().includes("new fee type"))).toBe(true);
    expect(unmapped[0]?.sourceValue).toBe("ABC");
    page.remove();
  });

  it("E: valid known blank stays valid_blank (not unmapped, not not_captured)", () => {
    const row = {
      id: 1,
      import_id: "x",
      row_type: "HEADER",
      source_page: 1,
      client_email: "",
    } as FuelBvdRow;
    const slot = {
      fuelBvdId: 1,
      fieldName: "client_email",
      selectionKey: "1:client_email",
      page: 1,
      rowType: "HEADER",
      sourceRowNumber: 0,
      left: 0,
      top: 0,
      width: 10,
      height: 10,
      ambiguous: false,
    };
    expect(getReviewFieldState(row, "client_email", slot)).toBe("valid_blank");
  });

  it("merges unmapped rows into shared line numbers by page position", () => {
    const header = { id: 1, import_id: "x", row_type: "HEADER", source_page: 1 } as FuelBvdRow;
    const unmapped = [
      {
        id: "1:new_fee",
        page: 1,
        label: "New Fee Type",
        sourceValue: "ABC",
        confidence: "high" as const,
        left: 10,
        top: 50,
        width: 100,
        height: 20,
        contextSnippet: "New Fee Type: ABC",
        selectionKey: "unmapped:1:new_fee",
      },
    ];
    const merged = buildReviewLogicalRowsMerged([header], unmapped, []);
    const unmappedLine = merged.find((l) => l.rowType === "UNMAPPED_SOURCE");
    expect(unmappedLine?.reviewLineNumber).toBeGreaterThan(0);
    expect(merged.length).toBe(BVD_HEADER_FIELDS.length + 1);
  });
});
