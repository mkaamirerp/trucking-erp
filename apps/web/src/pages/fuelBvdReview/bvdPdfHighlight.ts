/** Client-side PDF text-layer highlight lookup (no DB coordinates). */

export type PdfTextItem = {
  str: string;
  x: number;
  y: number;
  width: number;
  height: number;
  centerY: number;
};

export type PdfHighlightRect = {
  x: number;
  y: number;
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
  /** Stable row anchor (e.g. auth_code, invoice_number, row_label). */
  anchorField?: string;
  anchorValue?: string;
};

const ROW_Y_TOLERANCE = 28;

export function normalizePdfSearchText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

/** Build positioned items from pdf.js getTextContent() items. */
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

/** Also match values split across adjacent items on the same line (simple pair merge). */
export function findValueMatches(items: PdfTextItem[], value: string): PdfTextItem[] {
  const needle = normalizePdfSearchText(value);
  if (!needle) return [];

  const direct = items.filter((i) => itemMatchesValue(i, value));
  if (direct.length) return direct;

  const merged: PdfTextItem[] = [];
  for (let i = 0; i < items.length - 1; i += 1) {
    const a = items[i];
    const b = items[i + 1];
    if (Math.abs(a.centerY - b.centerY) > 4) continue;
    const combo = normalizePdfSearchText(`${a.str} ${b.str}`);
    if (combo === needle || combo.includes(needle)) {
      merged.push({
        str: combo,
        x: Math.min(a.x, b.x),
        y: Math.min(a.y, b.y),
        width: Math.max(a.x + a.width, b.x + b.width) - Math.min(a.x, b.x),
        height: Math.max(a.height, b.height),
        centerY: (a.centerY + b.centerY) / 2,
      });
    }
  }
  return merged;
}

export function findAnchorCenterY(items: PdfTextItem[], anchorValue: string | undefined): number | null {
  if (!anchorValue) return null;
  const matches = findValueMatches(items, anchorValue);
  if (matches.length === 1) return matches[0].centerY;
  if (matches.length > 1) {
    return matches[0].centerY;
  }
  return null;
}

/**
 * Pick the best PDF text match on a page using row anchor + vertical proximity.
 * Returns null when value is empty or no match; ambiguous=true when multiple equally likely.
 */
export function resolveHighlightOnPage(
  items: PdfTextItem[],
  ctx: HighlightLookupContext,
): Omit<PdfHighlightRect, "page"> | null {
  const value = normalizePdfSearchText(ctx.value);
  if (!value) return null;

  const matches = findValueMatches(items, value);
  if (!matches.length) return null;
  if (matches.length === 1) {
    const m = matches[0];
    return { x: m.x, y: m.y - m.height, width: m.width, height: m.height, ambiguous: false };
  }

  const anchorY = findAnchorCenterY(items, ctx.anchorValue);
  if (anchorY === null) {
    return { ambiguous: true, x: matches[0].x, y: matches[0].y - matches[0].height, width: matches[0].width, height: matches[0].height };
  }

  let best = matches[0];
  let bestDist = Math.abs(best.centerY - anchorY);
  let tie = false;
  for (const m of matches.slice(1)) {
    const dist = Math.abs(m.centerY - anchorY);
    if (dist < bestDist - 0.5) {
      best = m;
      bestDist = dist;
      tie = false;
    } else if (Math.abs(dist - bestDist) <= 0.5) {
      tie = true;
    }
  }

  if (tie && bestDist > ROW_Y_TOLERANCE) {
    return { ambiguous: true, x: best.x, y: best.y - best.height, width: best.width, height: best.height };
  }

  const ambiguous = tie || bestDist > ROW_Y_TOLERANCE;
  return {
    x: best.x,
    y: best.y - best.height,
    width: best.width,
    height: best.height,
    ambiguous,
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
