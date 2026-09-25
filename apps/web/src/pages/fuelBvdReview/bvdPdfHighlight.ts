/** BVD PDF highlight — semantic text matching (which occurrence), not screen coordinates. */

export type PdfTextItem = {
  str: string;
  x: number;
  y: number;
  width: number;
  height: number;
  centerY: number;
};

/** Display-space highlight relative to PDFPageView.div (set by DOM layer). */
export type PdfDisplayHighlightRect = {
  left: number;
  top: number;
  width: number;
  height: number;
  page: number;
  ambiguous: boolean;
};

export type HighlightLookupContext = {
  page: number;
  field: string;
  label: string;
  value: string;
  rowType: string;
  sourceRowNumber: number;
  /** Stable id for stale async guard: `${fuel_bvd_id}:${field}`. */
  selectionKey: string;
  anchorField?: string;
  anchorValue?: string;
  /** Grand Total row disambiguation when product code repeats (e.g. TA). */
  rowQtyHint?: string;
};

export type SemanticTextMatch = {
  /** Indices into the non-empty PdfTextItem[] aligned with text layer spans. */
  itemIndices: number[];
  ambiguous: boolean;
};

const ROW_Y_TOLERANCE = 28;

/** Column index relative to product cell on BVD Grand Total table rows (page 2). */
export const GRAND_TOTAL_COLUMN_OFFSET: Record<string, number> = {
  qty: 1,
  pre_tax_amt: 2,
  hst: 3,
  gst: 4,
  pst: 5,
  qst: 6,
  disc_rate: 7,
  disc_amt: 8,
  final_amount: 9,
  currency: 10,
};

function pickGrandTotalFieldByColumn(
  items: PdfTextItem[],
  ctx: HighlightLookupContext,
  anchorCenterY: number,
): SemanticTextMatch | null {
  const colOffset = GRAND_TOTAL_COLUMN_OFFSET[ctx.field];
  if (colOffset === undefined) return null;

  const rowEntries = items
    .map((it, i) => ({ it, i }))
    .filter(({ it }) => Math.abs(it.centerY - anchorCenterY) <= ROW_Y_TOLERANCE)
    .sort((a, b) => a.it.x - b.it.x);

  const productNeedle = normalizePdfSearchText(ctx.anchorValue ?? "");
  const productPos = rowEntries.findIndex(({ it }) => normalizePdfSearchText(it.str) === productNeedle);
  if (productPos < 0) return null;

  const valueNeedle = normalizePdfSearchText(ctx.value);
  let target = rowEntries[productPos + colOffset];
  if (ctx.field === "currency") {
    const currencyCells = rowEntries.filter(({ it }) => normalizePdfSearchText(it.str) === valueNeedle);
    if (currencyCells.length === 1) target = currencyCells[0];
    else if (currencyCells.length > 1) target = currencyCells[currencyCells.length - 1];
  }
  if (!target) return null;

  const targetText = normalizePdfSearchText(target.it.str);
  if (targetText !== valueNeedle && !targetText.includes(valueNeedle)) {
    return null;
  }

  const candidates = findValueMatchCandidates(items, ctx.value).filter((c) =>
    c.itemIndices.every((ix) => Math.abs(items[ix].centerY - anchorCenterY) <= ROW_Y_TOLERANCE),
  );
  const columnPick = candidates.find((c) => c.itemIndices[0] === target.i);
  if (columnPick) return { itemIndices: columnPick.itemIndices, ambiguous: false };

  return { itemIndices: [target.i], ambiguous: false };
}

export function normalizePdfSearchText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function mapPdfJsTextItems(
  raw: Array<{ str: string; transform: number[]; width: number; height: number }>,
): PdfTextItem[] {
  return raw
    .map((item) => {
      const x = item.transform[4];
      const y = item.transform[5];
      const w = item.width || Math.abs(item.transform[0]) || 1;
      const h = item.height || Math.abs(item.transform[3]) || 10;
      return {
        str: item.str,
        x,
        y,
        width: w,
        height: h,
        centerY: y - h / 2,
      };
    })
    .filter((i) => i.str.trim().length > 0);
}

function itemMatchesValue(item: PdfTextItem, value: string): boolean {
  const needle = normalizePdfSearchText(value);
  if (!needle) return false;
  const hay = normalizePdfSearchText(item.str);
  if (hay === needle) return true;
  if (hay.includes(needle) && needle.length >= 3) return true;
  return false;
}

export type ValueMatchCandidate = {
  itemIndices: number[];
  centerY: number;
};

/** Value matches as item index sets (single item or adjacent pair on one line). */
export function findValueMatchCandidates(items: PdfTextItem[], value: string): ValueMatchCandidate[] {
  const needle = normalizePdfSearchText(value);
  if (!needle) return [];

  const out: ValueMatchCandidate[] = [];
  const seen = new Set<string>();

  for (let i = 0; i < items.length; i += 1) {
    if (!itemMatchesValue(items[i], value)) continue;
    const key = String(i);
    if (!seen.has(key)) {
      seen.add(key);
      out.push({ itemIndices: [i], centerY: items[i].centerY });
    }
  }

  for (let i = 0; i < items.length - 1; i += 1) {
    const a = items[i];
    const b = items[i + 1];
    if (Math.abs(a.centerY - b.centerY) > 4) continue;
    const combo = normalizePdfSearchText(`${a.str} ${b.str}`);
    if (combo === needle) {
      const key = `${i},${i + 1}`;
      if (!seen.has(key)) {
        seen.add(key);
        out.push({ itemIndices: [i, i + 1], centerY: (a.centerY + b.centerY) / 2 });
      }
    }
  }

  return out;
}

/** @deprecated use findValueMatchCandidates */
export function findValueMatches(items: PdfTextItem[], value: string): PdfTextItem[] {
  return findValueMatchCandidates(items, value).map((c) => {
    const first = items[c.itemIndices[0]];
    if (c.itemIndices.length === 1) return first;
    const last = items[c.itemIndices[c.itemIndices.length - 1]];
    return {
      str: c.itemIndices.map((ix) => items[ix].str).join(" "),
      x: Math.min(first.x, last.x),
      y: Math.min(first.y, last.y),
      width: Math.max(first.x + first.width, last.x + last.width) - Math.min(first.x, last.x),
      height: Math.max(first.height, last.height),
      centerY: c.centerY,
    };
  });
}

function findAnchorItemIndices(
  items: PdfTextItem[],
  anchorValue: string | undefined,
  ctx?: HighlightLookupContext,
): number[] {
  if (!anchorValue) return [];
  const anchorNeedle = normalizePdfSearchText(anchorValue);
  if (!anchorNeedle) return [];

  const exactOnly =
    ctx?.rowType === "GRAND_TOTAL" &&
    (ctx.anchorField === "product" || ctx.anchorField === "legend_code");

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

/** When product code (e.g. TA) appears multiple times, pick the Grand Total table row. */
export function pickGrandTotalProductAnchorIndex(
  items: PdfTextItem[],
  product: string,
  rowQtyHint?: string,
): number | null {
  const needle = normalizePdfSearchText(product);
  const candidates = items
    .map((it, i) => ({ i, hay: normalizePdfSearchText(it.str) }))
    .filter(({ hay }) => hay === needle)
    .map(({ i }) => i);
  if (!candidates.length) return null;
  if (candidates.length === 1) return candidates[0];

  const qtyNeedle = rowQtyHint ? normalizePdfSearchText(rowQtyHint) : "";
  if (qtyNeedle) {
    const withQty = candidates.filter((pi) => {
      const rowY = items[pi].centerY;
      const rowItems = items.filter((it) => Math.abs(it.centerY - rowY) <= ROW_Y_TOLERANCE);
      const rowText = normalizePdfSearchText(rowItems.map((it) => it.str).join(" "));
      return rowText.includes(qtyNeedle);
    });
    if (withQty.length === 1) return withQty[0];
    if (withQty.length > 1) return null;
  }

  return null;
}

function pickCandidateNearAnchorY(
  candidates: ValueMatchCandidate[],
  anchorCenterY: number,
): SemanticTextMatch | null {
  let best = candidates[0];
  let bestDist = Math.abs(best.centerY - anchorCenterY);
  let tie = false;
  for (const c of candidates.slice(1)) {
    const dist = Math.abs(c.centerY - anchorCenterY);
    if (dist < bestDist - 0.5) {
      best = c;
      bestDist = dist;
      tie = false;
    } else if (Math.abs(dist - bestDist) <= 0.5) {
      tie = true;
    }
  }
  if (tie && bestDist > ROW_Y_TOLERANCE) {
    return { itemIndices: best.itemIndices, ambiguous: true };
  }
  const ambiguous = tie || bestDist > ROW_Y_TOLERANCE;
  return { itemIndices: best.itemIndices, ambiguous };
}

/**
 * Which text-layer item(s) correspond to this BVD field value (PDF user space for row banding only).
 */
export function resolveSemanticTextMatch(items: PdfTextItem[], ctx: HighlightLookupContext): SemanticTextMatch | null {
  const value = normalizePdfSearchText(ctx.value);
  if (!value) return null;

  const candidates = findValueMatchCandidates(items, value);
  if (!candidates.length) return null;
  if (candidates.length === 1) {
    return { itemIndices: candidates[0].itemIndices, ambiguous: false };
  }

  let anchorCenterY: number | null = null;
  if (ctx.rowType === "GRAND_TOTAL" && ctx.anchorField === "product" && ctx.anchorValue) {
    const pi = pickGrandTotalProductAnchorIndex(items, ctx.anchorValue, ctx.rowQtyHint);
    if (pi === null && findAnchorItemIndices(items, ctx.anchorValue, ctx).length > 1) {
      return { itemIndices: candidates[0].itemIndices, ambiguous: true };
    }
    if (pi !== null) anchorCenterY = items[pi].centerY;
  }

  if (anchorCenterY === null) {
    const anchorIndices = findAnchorItemIndices(items, ctx.anchorValue, ctx);
    if (anchorIndices.length === 1) {
      anchorCenterY = items[anchorIndices[0]].centerY;
    } else if (anchorIndices.length > 1) {
      return { itemIndices: candidates[0].itemIndices, ambiguous: true };
    }
  }

  if (anchorCenterY !== null) {
    if (ctx.rowType === "GRAND_TOTAL") {
      const columnPick = pickGrandTotalFieldByColumn(items, ctx, anchorCenterY);
      if (columnPick) return columnPick;
    }
    const inRow = candidates.filter((c) => Math.abs(c.centerY - anchorCenterY) <= ROW_Y_TOLERANCE);
    if (inRow.length === 1) {
      return { itemIndices: inRow[0].itemIndices, ambiguous: false };
    }
    if (inRow.length > 1) {
      return { itemIndices: inRow[0].itemIndices, ambiguous: true };
    }
    const picked = pickCandidateNearAnchorY(candidates, anchorCenterY);
    if (picked) return picked;
  }

  return { itemIndices: candidates[0].itemIndices, ambiguous: true };
}

/** Back-compat for unit tests that assert PDF-space y (semantic row band only). */
export function resolveHighlightOnPage(
  items: PdfTextItem[],
  ctx: HighlightLookupContext,
): Omit<PdfDisplayHighlightRect, "page" | "left" | "top" | "width" | "height"> & {
  x: number;
  y: number;
  width: number;
  height: number;
} | null {
  const match = resolveSemanticTextMatch(items, ctx);
  if (!match) return null;
  const first = items[match.itemIndices[0]];
  const last = items[match.itemIndices[match.itemIndices.length - 1]];
  return {
    x: Math.min(first.x, last.x),
    y: Math.min(first.y, last.y) - Math.max(first.height, last.height),
    width: Math.max(first.x + first.width, last.x + last.width) - Math.min(first.x, last.x),
    height: Math.max(first.height, last.height),
    ambiguous: match.ambiguous,
  };
}

export function anchorFieldForRowType(rowType: string): string | undefined {
  switch (rowType) {
    case "TRANSACTION":
      return "auth_code";
    case "HEADER":
      return "invoice_number";
    case "TRANSACTION_SUBTOTAL":
    case "PAGE1_SUMMARY":
      return "row_label";
    case "GRAND_TOTAL":
      return "product";
    case "LEGEND":
      return "legend_code";
    default:
      return undefined;
  }
}
