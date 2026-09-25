import type { HighlightLookupContext, PdfTextItem, ValueMatchCandidate } from "./bvdPdfHighlight";
import {
  findValueMatchCandidates,
  normalizePdfSearchText,
  pickGrandTotalProductAnchorIndex,
  resolveSemanticTextMatch,
} from "./bvdPdfHighlight";

function findAnchorItemIndices(items: PdfTextItem[], anchorValue: string | undefined, ctx: HighlightLookupContext): number[] {
  if (!anchorValue) return [];
  const anchorNeedle = normalizePdfSearchText(anchorValue);
  if (!anchorNeedle) return [];
  const exactOnly =
    ctx.rowType === "GRAND_TOTAL" && (ctx.anchorField === "product" || ctx.anchorField === "legend_code");
  const indices: number[] = [];
  for (let i = 0; i < items.length; i += 1) {
    const hay = normalizePdfSearchText(items[i].str);
    if (exactOnly) {
      if (hay === anchorNeedle) indices.push(i);
    } else if (hay === anchorNeedle || (hay.includes(anchorNeedle) && anchorNeedle.length >= 4)) {
      indices.push(i);
    }
  }
  return indices;
}

const HIGHLIGHT_PAD = 2;
const DOM_ROW_TOLERANCE_PX = 6;

export type DomHighlightRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

/** Leaf text spans under .textLayer in document order. */
export function getTextLayerSpanElements(pageDiv: HTMLElement): HTMLElement[] {
  const layer = pageDiv.querySelector(".textLayer");
  if (!layer) return [];
  const spans: HTMLElement[] = [];
  layer.querySelectorAll("span").forEach((el) => {
    if (el.tagName !== "SPAN") return;
    if (el.classList.contains("markedContent")) return;
    if (el.querySelector("span")) return;
    spans.push(el as HTMLElement);
  });
  return spans;
}

/**
 * Map each PdfTextItem index to one or more rendered spans (handles split values).
 * Verified against 972201: usually 1:1; falls back to greedy text alignment when counts differ.
 */
export function buildItemIndexToSpanElements(
  items: PdfTextItem[],
  spans: HTMLElement[],
): Map<number, HTMLElement[]> {
  const map = new Map<number, HTMLElement[]>();
  if (!spans.length || !items.length) return map;

  if (spans.length === items.length) {
    for (let i = 0; i < items.length; i += 1) {
      map.set(i, [spans[i]]);
    }
    return map;
  }

  let spanIdx = 0;
  for (let itemIdx = 0; itemIdx < items.length; itemIdx += 1) {
    const target = normalizePdfSearchText(items[itemIdx].str);
    if (!target) continue;
    const used: HTMLElement[] = [];
    let combined = "";
    while (spanIdx < spans.length && combined !== target) {
      used.push(spans[spanIdx]);
      combined = normalizePdfSearchText(used.map((s) => s.textContent ?? "").join(""));
      spanIdx += 1;
      if (combined.length > target.length + 8) break;
    }
    if (combined === target && used.length) {
      map.set(itemIdx, used);
    } else if (spanIdx > 0) {
      spanIdx -= 1;
    }
  }
  return map;
}

function unionClientRects(rects: DOMRect[]): DOMRect | null {
  if (!rects.length) return null;
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  for (const r of rects) {
    if (r.width === 0 && r.height === 0) continue;
    left = Math.min(left, r.left);
    top = Math.min(top, r.top);
    right = Math.max(right, r.right);
    bottom = Math.max(bottom, r.bottom);
  }
  if (left === Infinity) return null;
  return new DOMRect(left, top, right - left, bottom - top);
}

export function spanElementsForItemIndices(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  itemIndices: number[],
): HTMLElement[] {
  const spans = getTextLayerSpanElements(pageDiv);
  const map = buildItemIndexToSpanElements(items, spans);
  const out: HTMLElement[] = [];
  for (const ix of itemIndices) {
    const els = map.get(ix);
    if (els?.length) out.push(...els);
    else if (spans[ix]) out.push(spans[ix]);
  }
  return out;
}

function rectsForItemIndices(pageDiv: HTMLElement, items: PdfTextItem[], itemIndices: number[]): DOMRect | null {
  const elements = spanElementsForItemIndices(pageDiv, items, itemIndices);
  if (!elements.length) return null;
  return unionClientRects(elements.map((el) => el.getBoundingClientRect()));
}

function disambiguateWithDomRow(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  candidates: ValueMatchCandidate[],
  anchorItemIndices: number[],
): number[] | null {
  if (!candidates.length) return null;
  const anchorRect = rectsForItemIndices(pageDiv, items, anchorItemIndices);
  if (!anchorRect) return null;
  const anchorMidY = anchorRect.top + anchorRect.height / 2;
  const inRow = candidates.filter((c) => {
    const r = rectsForItemIndices(pageDiv, items, c.itemIndices);
    if (!r) return false;
    const midY = r.top + r.height / 2;
    return Math.abs(midY - anchorMidY) <= DOM_ROW_TOLERANCE_PX;
  });
  if (inRow.length === 1) return inRow[0].itemIndices;
  return null;
}

function resolveAnchorItemIndices(items: PdfTextItem[], ctx: HighlightLookupContext): number[] {
  if (ctx.rowType === "GRAND_TOTAL" && ctx.anchorField === "product" && ctx.anchorValue) {
    const pi = pickGrandTotalProductAnchorIndex(items, ctx.anchorValue, ctx.rowQtyHint);
    if (pi !== null) return [pi];
    const all = findAnchorItemIndices(items, ctx.anchorValue, ctx);
    return all.length === 1 ? all : [];
  }
  const all = findAnchorItemIndices(items, ctx.anchorValue, ctx);
  return all.length === 1 ? all : all;
}

/**
 * Final highlight box in coordinates relative to PDFPageView.div (DOM geometry only).
 */
export function resolveDomHighlightRect(
  pageDiv: HTMLElement,
  items: PdfTextItem[],
  ctx: HighlightLookupContext,
): { rect: DomHighlightRect | null; ambiguous: boolean } {
  const semantic = resolveSemanticTextMatch(items, ctx);
  if (!semantic) return { rect: null, ambiguous: false };

  let itemIndices = semantic.itemIndices;
  let ambiguous = semantic.ambiguous;

  if (ambiguous) {
    const value = normalizePdfSearchText(ctx.value);
    const candidates = findValueMatchCandidates(items, value);
    const anchorIdx = resolveAnchorItemIndices(items, ctx);
    if (candidates.length > 1 && anchorIdx.length === 1) {
      const domPick = disambiguateWithDomRow(pageDiv, items, candidates, anchorIdx);
      if (domPick) {
        itemIndices = domPick;
        ambiguous = false;
      }
    }
  }

  if (ambiguous) return { rect: null, ambiguous: true };

  const pageRect = pageDiv.getBoundingClientRect();
  const valueRect = rectsForItemIndices(pageDiv, items, itemIndices);
  if (!valueRect) return { rect: null, ambiguous: true };

  const left = valueRect.left - pageRect.left - HIGHLIGHT_PAD;
  const top = valueRect.top - pageRect.top - HIGHLIGHT_PAD;
  const width = valueRect.width + HIGHLIGHT_PAD * 2;
  const height = valueRect.height + HIGHLIGHT_PAD * 2;

  return {
    rect: { left, top, width, height },
    ambiguous: false,
  };
}

export function scrollContainerToHighlight(
  scrollEl: HTMLElement,
  pageDiv: HTMLElement,
  rect: DomHighlightRect,
): void {
  const pageRect = pageDiv.getBoundingClientRect();
  const scrollRect = scrollEl.getBoundingClientRect();
  const highlightTopInScroll =
    scrollEl.scrollTop + (pageRect.top - scrollRect.top) + rect.top + rect.height / 2;
  const target = highlightTopInScroll - scrollEl.clientHeight / 2;
  scrollEl.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
}
