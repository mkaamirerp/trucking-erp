/**
 * Client-side discovery of PDF source labels not in the known BVD review contract.
 * Conservative: prefer missing high-confidence label/value pairs over false positives.
 */

import { BVD_FIELD_LABELS, BVD_TRANSACTION_COLUMNS } from "../fuelBvdReviewLabels";
import type { BvdFieldSlot } from "./bvdFieldSlots";
import { normalizePdfSearchText, type PdfTextItem } from "./bvdPdfHighlight";
import { spanElementsForItemIndices, toPageCoordsFromDom } from "./bvdUnmappedSourceGeom";

export type BvdUnmappedSourceField = {
  id: string;
  page: number;
  label: string;
  sourceValue: string | null;
  confidence: "high";
  left: number;
  top: number;
  width: number;
  height: number;
  contextSnippet: string;
  selectionKey: string;
};

export type BvdPossibleUnmappedContent = {
  page: number;
  contextSnippet: string;
  reason: string;
};

const ROW_Y_TOL = 6;

const GRAND_TOTAL_HEADER_LABELS = [
  "PRODUCT",
  "QTY",
  "PRE TAX AMT",
  "HST",
  "GST",
  "PST",
  "QST",
  "DISC RATE",
  "DISC AMT",
  "FINAL AMOUNT",
  "CUR",
];

const EXTRA_KNOWN_TABLE_LABELS = [
  "Auth Code",
  "Driver Name",
  "Unit #",
  "Date",
  "Site #",
  "Site Name",
  "Site City",
  "Prov/ST",
  "Prod",
  "Retail",
  "Billed",
  "Pre Tax AMT",
  "Disc Rate",
  "Disc AMT",
  "Final AMT",
  "Label",
  "Code",
  "Product Name",
];

const HEADER_LABEL_PARTS = [
  "Invoice",
  "Number",
  "Date",
  "Start",
  "End",
  "Due",
  "Client",
  "Address",
  "Phone",
  "Email",
  "Card",
  "HST",
  "QST",
];

const DECORATIVE_SUBSTRINGS = [
  "nationwide",
  "fuel card",
  "billing statement",
  "transaction detail",
  "grand total",
  "legend",
  "continued",
  "statement of",
  "all rights",
  "copyright",
  "remit to",
  "please pay",
  "subtotal",
  "page ",
  "bvd ",
];

export function normalizeSourceLabel(text: string): string {
  return normalizePdfSearchText(text).toLowerCase().replace(/:$/, "").trim();
}

export function buildKnownBvdSourceLabels(): Set<string> {
  const known = new Set<string>();
  for (const v of Object.values(BVD_FIELD_LABELS)) known.add(normalizeSourceLabel(v));
  for (const c of BVD_TRANSACTION_COLUMNS) known.add(normalizeSourceLabel(c.label));
  for (const h of GRAND_TOTAL_HEADER_LABELS) known.add(normalizeSourceLabel(h));
  for (const h of EXTRA_KNOWN_TABLE_LABELS) known.add(normalizeSourceLabel(h));
  for (const h of HEADER_LABEL_PARTS) known.add(normalizeSourceLabel(h));
  return known;
}

function isKnownLabel(label: string, known: Set<string>): boolean {
  const n = normalizeSourceLabel(label);
  if (known.has(n)) return true;
  for (const k of known) {
    if (n.includes(k) && k.length >= 4) return true;
    if (k.includes(n) && n.length >= 4) return true;
  }
  return false;
}

export function isDecorativeLineText(combined: string): boolean {
  const n = normalizeSourceLabel(combined);
  if (!n || n.length < 3) return true;
  if (/^page\s*\d+$/i.test(n)) return true;
  if (/^\d{1,3}$/.test(n)) return true;
  for (const d of DECORATIVE_SUBSTRINGS) {
    if (n.includes(d)) return true;
  }
  return false;
}

function groupItemsByLine(items: PdfTextItem[]): PdfTextItem[][] {
  const sorted = [...items].sort((a, b) => b.centerY - a.centerY || a.x - b.x);
  const lines: PdfTextItem[][] = [];
  for (const it of sorted) {
    const line = lines.find((ln) => Math.abs(ln[0].centerY - it.centerY) <= ROW_Y_TOL);
    if (line) line.push(it);
    else lines.push([it]);
  }
  for (const ln of lines) ln.sort((a, b) => a.x - b.x);
  return lines;
}

function findAuthHeaderY(items: PdfTextItem[]): number | null {
  for (const it of items) {
    const n = normalizeSourceLabel(it.str);
    if (n === "auth code" || n.includes("auth code")) return it.centerY;
  }
  return null;
}

function isKnownColumnHeaderRow(line: PdfTextItem[], known: Set<string>): boolean {
  if (line.length < 3) return false;
  let knownCount = 0;
  for (const it of line) {
    if (isKnownLabel(it.str, known)) knownCount += 1;
  }
  return knownCount >= Math.min(3, line.length);
}

function looksLikeTransactionDataLine(line: PdfTextItem[]): boolean {
  const joined = line.map((i) => i.str).join(" ");
  if (/-TA\b/i.test(joined)) return true;
  if (/\d{1,3},\d{3}\.\d{2}/.test(joined) && line.length >= 4) return true;
  return false;
}

function parseLabelValueLine(line: PdfTextItem[]): { label: string; value: string | null } | null {
  const text = line.map((i) => i.str).join(" ").trim();
  const colon = text.match(/^(.{4,}?):\s*(.+)$/);
  if (colon) {
    return { label: colon[1].trim(), value: colon[2].trim() };
  }
  if (line.length < 2) return null;
  const mid = Math.max(1, Math.floor(line.length / 2));
  const left = line.slice(0, mid).map((i) => i.str).join(" ").trim();
  const right = line.slice(mid).map((i) => i.str).join(" ").trim();
  if (left.length < 4 || !right) return null;
  if (/^\d+([.,]\d+)?$/.test(left) && !left.includes(" ")) return null;
  return { label: left.replace(/:$/, ""), value: right };
}

function geomForLine(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  line: PdfTextItem[],
  indices: number[],
): { left: number; top: number; width: number; height: number } {
  const dom = spanElementsForItemIndices(pageDiv, items, indices);
  if (dom.length) {
    let l = Infinity;
    let t = Infinity;
    let r = -Infinity;
    let b = -Infinity;
    for (const el of dom) {
      const rect = el.getBoundingClientRect();
      l = Math.min(l, rect.left);
      t = Math.min(t, rect.top);
      r = Math.max(r, rect.right);
      b = Math.max(b, rect.bottom);
    }
    if (l !== Infinity) return toPageCoordsFromDom(pageDiv, new DOMRect(l, t, r - l, b - t));
  }
  const left = Math.min(...line.map((i) => i.x));
  const top = Math.min(...line.map((i) => i.y - i.height));
  const right = Math.max(...line.map((i) => i.x + (i.width || 40)));
  return { left, top, width: Math.max(right - left, 40), height: 14 };
}

export type UnmappedDiscoveryResult = {
  unmapped: BvdUnmappedSourceField[];
  possible: BvdPossibleUnmappedContent[];
};

export function discoverUnmappedSourceFields(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  page: number,
  slots: BvdFieldSlot[],
): UnmappedDiscoveryResult {
  const known = buildKnownBvdSourceLabels();
  const authY = findAuthHeaderY(items);
  const unmapped: BvdUnmappedSourceField[] = [];
  const possible: BvdPossibleUnmappedContent[] = [];
  const seenLabels = new Set<string>();

  const slotLabels = new Set<string>();
  for (const s of slots) {
    const label = BVD_FIELD_LABELS[s.fieldName];
    if (label) slotLabels.add(normalizeSourceLabel(label));
  }

  for (const line of groupItemsByLine(items)) {
    const combined = line.map((i) => i.str).join(" ");
    if (isDecorativeLineText(combined)) continue;
    if (isKnownColumnHeaderRow(line, known)) continue;
    if (looksLikeTransactionDataLine(line)) continue;

    const lineY = line[0].centerY;
    if (authY !== null && lineY <= authY + ROW_Y_TOL) continue;
    if (authY !== null && lineY < authY && looksLikeTransactionDataLine(line)) continue;

    const parsed = parseLabelValueLine(line);
    if (!parsed) {
      if (line.length === 1 && line[0].str.length >= 8 && /[A-Za-z]/.test(line[0].str) && !isKnownLabel(line[0].str, known)) {
        possible.push({
          page,
          contextSnippet: line[0].str.slice(0, 80),
          reason: "possible unmapped source content",
        });
      }
      continue;
    }

    if (isKnownLabel(parsed.label, known)) continue;
    if (slotLabels.has(normalizeSourceLabel(parsed.label))) continue;

    const norm = normalizeSourceLabel(parsed.label);
    if (seenLabels.has(norm)) continue;
    seenLabels.add(norm);

    const indices = line.map((it) => items.findIndex((x) => x === it)).filter((i) => i >= 0);
    const geom = geomForLine(pageDiv, items, line, indices.length ? indices : []);
    const id = `${page}:${norm.replace(/\s+/g, "_")}`;
    unmapped.push({
      id,
      page,
      label: parsed.label,
      sourceValue: parsed.value,
      confidence: "high",
      ...geom,
      contextSnippet: combined.slice(0, 120),
      selectionKey: `unmapped:${id}`,
    });
  }

  return { unmapped, possible };
}

export function unmappedSelectionKey(field: BvdUnmappedSourceField): string {
  return field.selectionKey;
}
