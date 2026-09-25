/** Client-side BVD field slot geometry (not persisted). */

import type { FuelBvdRow } from "../../api";
import {
  BVD_GRAND_TOTAL_FIELDS,
  BVD_HEADER_FIELDS,
  BVD_SUBTOTAL_FIELDS,
  BVD_TRANSACTION_COLUMNS,
  BVD_FIELD_LABELS,
} from "../fuelBvdReviewLabels";
import type { PdfTextItem } from "./bvdPdfHighlight";
import { normalizePdfSearchText, pickGrandTotalProductAnchorIndex } from "./bvdPdfHighlight";
import {
  BVD_GRAND_TOTAL_PROFILE_COLUMN_ORDER,
  BVD_GRAND_TOTAL_PROFILE_COLUMN_WIDTH,
} from "./bvdGrandTotalLayoutProfile";
import { buildItemIndexToSpanElements, getTextLayerSpanElements, spanElementsForItemIndices } from "./bvdPdfDomHighlight";

export type BvdFieldRef = {
  fuelBvdId: number;
  fieldName: string;
  selectionKey: string;
  page: number;
  rowType: string;
  sourceRowNumber: number;
};

export type BvdFieldSlot = BvdFieldRef & {
  left: number;
  top: number;
  width: number;
  height: number;
  ambiguous: boolean;
};

export type ColumnBand = {
  field: string;
  left: number;
  right: number;
};

const ROW_Y_TOL = 6;

export function fieldRef(row: FuelBvdRow, fieldName: string): BvdFieldRef {
  return {
    fuelBvdId: row.id,
    fieldName,
    selectionKey: `${row.id}:${fieldName}`,
    page: row.source_page ?? 1,
    rowType: row.row_type,
    sourceRowNumber: row.source_row_number ?? 0,
  };
}

export function fieldsForRowType(rowType: string): string[] {
  switch (rowType) {
    case "HEADER":
      return BVD_HEADER_FIELDS;
    case "TRANSACTION":
      return BVD_TRANSACTION_COLUMNS.map((c) => c.field);
    case "TRANSACTION_SUBTOTAL":
    case "PAGE1_SUMMARY":
      return BVD_SUBTOTAL_FIELDS;
    case "GRAND_TOTAL":
      return BVD_GRAND_TOTAL_FIELDS;
    case "LEGEND":
      return ["legend_code", "legend_product_name"];
    default:
      return [];
  }
}

export function orderedFieldRefsForRows(rows: FuelBvdRow[]): BvdFieldRef[] {
  const typeOrder = ["HEADER", "TRANSACTION", "TRANSACTION_SUBTOTAL", "PAGE1_SUMMARY", "GRAND_TOTAL", "LEGEND"];
  const out: BvdFieldRef[] = [];
  for (const rt of typeOrder) {
    const group = rows
      .filter((r) => r.row_type === rt)
      .sort((a, b) => (a.source_page ?? 1) - (b.source_page ?? 1) || (a.source_row_number ?? 0) - (b.source_row_number ?? 0));
    for (const row of group) {
      for (const field of fieldsForRowType(row.row_type)) {
        out.push(fieldRef(row, field));
      }
    }
  }
  return out;
}

function itemDomRect(pageDiv: HTMLElement, items: PdfTextItem[], indices: number[]): DOMRect | null {
  const els = spanElementsForItemIndices(pageDiv, items, indices);
  if (!els.length) return null;
  let l = Infinity;
  let t = Infinity;
  let r = -Infinity;
  let b = -Infinity;
  for (const el of els) {
    const rect = el.getBoundingClientRect();
    l = Math.min(l, rect.left);
    t = Math.min(t, rect.top);
    r = Math.max(r, rect.right);
    b = Math.max(b, rect.bottom);
  }
  if (l === Infinity) return null;
  return new DOMRect(l, t, r - l, b - t);
}

function toPageCoords(pageDiv: HTMLElement, client: DOMRect): { left: number; top: number; width: number; height: number } {
  const pr = pageDiv.getBoundingClientRect();
  return {
    left: client.left - pr.left,
    top: client.top - pr.top,
    width: client.width,
    height: client.height,
  };
}

function findHeaderLabelIndex(items: PdfTextItem[], label: string): number {
  const needle = normalizePdfSearchText(label).toLowerCase();
  for (let i = 0; i < items.length; i += 1) {
    const hay = normalizePdfSearchText(items[i].str).toLowerCase();
    if (hay === needle || hay.includes(needle)) return i;
  }
  return -1;
}

function findTransactionColumnBands(items: PdfTextItem[]): ColumnBand[] {
  const bands: ColumnBand[] = [];
  const indices: { field: string; i: number; x: number }[] = [];
  for (const col of BVD_TRANSACTION_COLUMNS) {
    const i = findHeaderLabelIndex(items, col.label);
    if (i >= 0) indices.push({ field: col.field, i, x: items[i].x });
  }
  indices.sort((a, b) => a.x - b.x);
  for (let j = 0; j < indices.length; j += 1) {
    const left = indices[j].x - 2;
    const right = j < indices.length - 1 ? indices[j + 1].x - 2 : indices[j].x + (items[indices[j].i].width || 40) + 80;
    bands.push({ field: indices[j].field, left, right });
  }
  return bands;
}

function findGrandTotalColumnBands(items: PdfTextItem[]): ColumnBand[] {
  const bands: ColumnBand[] = [];
  const headers: { field: string; label: string }[] = [
    { field: "product", label: "PRODUCT" },
    { field: "qty", label: "QTY" },
    { field: "pre_tax_amt", label: "PRE TAX AMT" },
    { field: "hst", label: "HST" },
    { field: "gst", label: "GST" },
    { field: "pst", label: "PST" },
    { field: "qst", label: "QST" },
    { field: "disc_rate", label: "DISC RATE" },
    { field: "disc_amt", label: "DISC AMT" },
    { field: "final_amount", label: "FINAL AMOUNT" },
    { field: "cur", label: "CUR" },
  ];
  const indices: { field: string; i: number; x: number }[] = [];
  for (const h of headers) {
    const i = findHeaderLabelIndex(items, h.label);
    if (i >= 0) indices.push({ field: h.field, i, x: items[i].x });
  }
  indices.sort((a, b) => a.x - b.x);
  for (let j = 0; j < indices.length; j += 1) {
    const left = indices[j].x - 2;
    const right = j < indices.length - 1 ? indices[j + 1].x - 2 : indices[j].x + 120;
    bands.push({ field: indices[j].field, left, right });
  }
  return bands;
}

function buildGrandTotalColumnBandsFromProfile(productAnchorX: number): ColumnBand[] {
  return BVD_GRAND_TOTAL_PROFILE_COLUMN_ORDER.map((field, i) => ({
    field,
    left: productAnchorX + i * BVD_GRAND_TOTAL_PROFILE_COLUMN_WIDTH,
    right: productAnchorX + (i + 1) * BVD_GRAND_TOTAL_PROFILE_COLUMN_WIDTH,
  }));
}

function rowBandFromAuth(items: PdfTextItem[], authCode: string): { centerY: number; height: number } | null {
  const needle = normalizePdfSearchText(authCode);
  if (!needle) return null;
  for (const it of items) {
    if (normalizePdfSearchText(it.str) === needle || normalizePdfSearchText(it.str).includes(needle)) {
      return { centerY: it.centerY, height: Math.max(it.height, 10) };
    }
  }
  return null;
}

function rowBandFromAuthOrdinal(items: PdfTextItem[], ordinal: number): { centerY: number; height: number } | null {
  const authLike = items.filter((it) => /-TA$/.test(normalizePdfSearchText(it.str)) || it.str.includes("-"));
  const sorted = [...authLike].sort((a, b) => b.centerY - a.centerY);
  const pick = sorted[ordinal];
  if (!pick) return null;
  return { centerY: pick.centerY, height: Math.max(pick.height, 10) };
}

function slotFromColumnRow(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  band: ColumnBand,
  row: { centerY: number; height: number },
  fieldIndexGuess: number[],
): { left: number; top: number; width: number; height: number } {
  const rowItems = items
    .map((it, i) => ({ it, i }))
    .filter(({ it }) => Math.abs(it.centerY - row.centerY) <= ROW_Y_TOL && it.x >= band.left && it.x < band.right);
  const indices = rowItems.length ? rowItems.map(({ i }) => i) : fieldIndexGuess;
  const dom = itemDomRect(pageDiv, items, indices.length ? indices : fieldIndexGuess);
  if (dom) return toPageCoords(pageDiv, dom);
  const pr = pageDiv.getBoundingClientRect();
  return {
    left: band.left - pr.left,
    top: row.centerY - row.height - pr.top,
    width: Math.max(band.right - band.left, 24),
    height: Math.max(row.height, 12),
  };
}

function buildHeaderSlots(pageDiv: HTMLElement, items: PdfTextItem[], row: FuelBvdRow): BvdFieldSlot[] {
  const slots: BvdFieldSlot[] = [];
  const labelMap: Record<string, string[]> = {
    invoice_number: ["Invoice", "Number"],
    invoice_date: ["Invoice", "Date"],
    start_date: ["Start", "Date"],
    end_date: ["End", "Date"],
    due_date: ["Due", "Date"],
    card_number: ["Card"],
    hst_number: ["HST"],
    qst_number: ["QST"],
    client_name: ["Client"],
    client_address: ["Address"],
    client_phone: ["Phone"],
    client_email: ["Email"],
  };
  for (const field of BVD_HEADER_FIELDS) {
    const labels = labelMap[field] ?? [BVD_FIELD_LABELS[field] ?? field];
    let labelIdx = -1;
    for (const part of labels) {
      const i = findHeaderLabelIndex(items, part);
      if (i >= 0) {
        labelIdx = i;
        break;
      }
    }
    let ambiguous = labelIdx < 0;
    let geom = { left: 0, top: 0, width: 80, height: 14 };
    if (labelIdx >= 0) {
      const labelItem = items[labelIdx];
      const sameLine = items
        .map((it, i) => ({ it, i }))
        .filter(({ it }) => Math.abs(it.centerY - labelItem.centerY) <= ROW_Y_TOL && it.x > labelItem.x + 20)
        .sort((a, b) => a.it.x - b.it.x);
      const valueIdx = sameLine[0]?.i;
      const dom = valueIdx !== undefined ? itemDomRect(pageDiv, items, [valueIdx]) : null;
      if (dom) geom = toPageCoords(pageDiv, dom);
      else ambiguous = true;
    }
    slots.push({
      ...fieldRef(row, field),
      ...geom,
      ambiguous,
    });
  }
  return slots;
}

function buildTransactionSlots(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  row: FuelBvdRow,
  txnOrdinal: number,
  authCode: string,
): BvdFieldSlot[] {
  const bands = findTransactionColumnBands(items);
  const rowBand = rowBandFromAuth(items, authCode) ?? rowBandFromAuthOrdinal(items, txnOrdinal);
  if (!rowBand || !bands.length) {
    return fieldsForRowType("TRANSACTION").map((field) => ({
      ...fieldRef(row, field),
      left: 0,
      top: 0,
      width: 40,
      height: 12,
      ambiguous: true,
    }));
  }
  return bands.map((band) => {
    const colItems = items
      .map((it, i) => ({ it, i }))
      .filter(({ it }) => Math.abs(it.centerY - rowBand.centerY) <= ROW_Y_TOL && it.x >= band.left && it.x < band.right);
    const geom =
      slotFromColumnRow(pageDiv, items, band, rowBand, colItems.map(({ i }) => i)) ??
      ({ left: band.left, top: rowBand.centerY - rowBand.height, width: band.right - band.left, height: rowBand.height } as const);
    return {
      ...fieldRef(row, band.field),
      ...geom,
      ambiguous: false,
    };
  });
}

function buildGrandTotalSlots(pageDiv: HTMLElement, items: PdfTextItem[], row: FuelBvdRow, product: string, qtyHint?: string): BvdFieldSlot[] {
  let bands = findGrandTotalColumnBands(items);
  const pi = pickGrandTotalProductAnchorIndex(items, product, qtyHint);
  const ambiguousAnchor = pi === null;
  if (bands.length < 5 && pi !== null) {
    bands = buildGrandTotalColumnBandsFromProfile(items[pi].x);
  }
  const centerY = pi !== null ? items[pi].centerY : items[0]?.centerY ?? 0;
  const rowBand = { centerY, height: 12 };
  return BVD_GRAND_TOTAL_FIELDS.map((field) => {
    const band = bands.find((b) => b.field === field);
    if (!band) {
      return { ...fieldRef(row, field), left: 0, top: 0, width: 40, height: 12, ambiguous: true };
    }
    const colItems = items
      .map((it, i) => ({ it, i }))
      .filter(({ it }) => Math.abs(it.centerY - rowBand.centerY) <= ROW_Y_TOL && it.x >= band!.left && it.x < band!.right);
    const geom =
      slotFromColumnRow(pageDiv, items, band, rowBand, colItems.map(({ i }) => i)) ??
      ({ left: band.left, top: rowBand.centerY - 6, width: band.right - band.left, height: 12 } as const);
    return {
      ...fieldRef(row, field),
      ...geom,
      ambiguous: ambiguousAnchor,
    };
  });
}

export function buildFieldSlotsForPage(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  rowsOnPage: FuelBvdRow[],
): BvdFieldSlot[] {
  getTextLayerSpanElements(pageDiv);
  buildItemIndexToSpanElements(items, getTextLayerSpanElements(pageDiv));

  const slots: BvdFieldSlot[] = [];
  const txns = rowsOnPage.filter((r) => r.row_type === "TRANSACTION").sort((a, b) => (a.source_row_number ?? 0) - (b.source_row_number ?? 0));
  let txnOrd = 0;
  for (const row of rowsOnPage) {
    if (row.row_type === "HEADER") slots.push(...buildHeaderSlots(pageDiv, items, row));
    else if (row.row_type === "TRANSACTION") {
      const auth = row.auth_code ?? "";
      slots.push(...buildTransactionSlots(pageDiv, items, row, txnOrd, auth));
      txnOrd += 1;
    } else if (row.row_type === "GRAND_TOTAL") {
      slots.push(...buildGrandTotalSlots(pageDiv, items, row, row.product ?? "TA", row.qty));
    } else if (row.row_type === "LEGEND") {
      for (const field of ["legend_code", "legend_product_name"]) {
        const label = field === "legend_code" ? "Code" : "Product Name";
        const idx = findHeaderLabelIndex(items, label);
        slots.push({
          ...fieldRef(row, field),
          left: idx >= 0 ? items[idx].x : 0,
          top: idx >= 0 ? items[idx].y - 20 : 0,
          width: 80,
          height: 12,
          ambiguous: idx < 0,
        });
      }
    } else if (row.row_type === "TRANSACTION_SUBTOTAL" || row.row_type === "PAGE1_SUMMARY") {
      for (const field of BVD_SUBTOTAL_FIELDS) {
        slots.push({ ...fieldRef(row, field), left: 0, top: 0, width: 60, height: 12, ambiguous: true });
      }
    }
  }
  return slots;
}

export function slotForRef(slots: BvdFieldSlot[], ref: BvdFieldRef | null): BvdFieldSlot | null {
  if (!ref) return null;
  return slots.find((s) => s.selectionKey === ref.selectionKey) ?? null;
}
