import { parseBvdMoneyString } from "../fuelBvdReview/bvdParsedValidation";

const CARD_TOTAL_LINE_RE = /^X+\d+\s+Total\b/i;
const MONEY_TWO_DEC_RE = /\$([\d,]+\.\d{2})/g;
const GST_IN_LINE_RE = /\bGST\s*\$?([\d,]+\.?\d*)/i;
const QST_IN_LINE_RE = /\bQST\s*\$?([\d,]+\.?\d*)/i;
const CARD_TOTAL_VOLUME_RE =
  /\bTotal\b(?:\s+GST\s*\$?[\d,]+\.?\d*)?(?:\s+QST\s*\$?[\d,]+\.?\d*)?\s+([\d,]+\.\d{2})\b/i;

export type ParsedNationwideCardTotal = {
  cardNumber: string;
  currency: "CAD" | "USD";
  gst: string | null;
  qst: string | null;
  declaredAmount: string | null;
};

function normalizeMoneyText(raw: string): string {
  const n = parseBvdMoneyString(raw.replace(/\$/g, ""));
  if (n === null) return raw.trim();
  return (Math.round(n * 100) / 100).toFixed(2);
}

/** Match backend `parse_nationwide_card_total_line` for CARD_TOTAL control lines. */
export function parseNationwideCardTotalLine(line: string | null | undefined): ParsedNationwideCardTotal | null {
  const stripped = (line ?? "").trim();
  if (!stripped || !CARD_TOTAL_LINE_RE.test(stripped)) return null;

  const cardNumber = stripped.split(/\s+/)[0] ?? "";
  const hasGst = GST_IN_LINE_RE.test(stripped);
  const currency: "CAD" | "USD" = hasGst ? "CAD" : "USD";

  const gstMatch = stripped.match(GST_IN_LINE_RE);
  const qstMatch = stripped.match(QST_IN_LINE_RE);
  const gst = gstMatch ? normalizeMoneyText(gstMatch[1]) : null;
  const qstRaw = qstMatch ? normalizeMoneyText(qstMatch[1]) : null;
  const qst = qstRaw && qstRaw !== "0.00" && qstRaw !== "0" ? qstRaw : null;

  const namedTax = new Set([gst, qst].filter(Boolean) as string[]);
  const twoDec: string[] = [];
  for (const m of stripped.matchAll(MONEY_TWO_DEC_RE)) {
    const v = normalizeMoneyText(m[1]);
    if (v) twoDec.push(v);
  }
  const positional = twoDec.filter((v) => !namedTax.has(v));
  const declaredAmount = positional[0] ?? null;

  return { cardNumber, currency, gst, qst, declaredAmount };
}

/** Align `X87195` with `XXXXX87195` for card-level tax lookup. */
export function normalizeNationwideCardKey(card: string | null | undefined): string {
  const digits = (card ?? "").replace(/\D/g, "");
  if (digits) return digits;
  return (card ?? "").trim().toUpperCase();
}

export type NationwideCardTaxBundle = {
  currency: string | null;
  gst: number | null;
  pst: number | null;
  qst: number | null;
  hst: number | null;
};

function moneyFromRowOrParsed(
  rowValue: string | null | undefined,
  parsed: string | null,
): number | null {
  const fromRow = parseBvdMoneyString(rowValue ?? "");
  if (fromRow !== null && Math.abs(fromRow) > 0.005) return fromRow;
  if (parsed) return parseBvdMoneyString(parsed);
  return fromRow;
}

/** CARD_TOTAL / control rows → per-card GST/PST/QST/HST for purchase-line attribution. */
export function buildNationwideCardTaxLedger(
  rows: Array<{
    row_type?: string | null;
    control_type?: string | null;
    control_line_raw?: string | null;
    row_label?: string | null;
    card_number?: string | null;
    currency?: string | null;
    gst?: string | null;
    pst?: string | null;
    qst?: string | null;
  }>,
): Map<string, NationwideCardTaxBundle> {
  const map = new Map<string, NationwideCardTaxBundle>();

  for (const r of rows) {
    const line = r.control_line_raw ?? r.row_label ?? "";
    const parsed = parseNationwideCardTotalLine(line);
    const isCardTotal = r.control_type === "CARD_TOTAL" || parsed !== null;
    if (!isCardTotal) continue;
    const cardKey = normalizeNationwideCardKey(parsed?.cardNumber ?? r.card_number);
    if (!cardKey) continue;

    const bundle: NationwideCardTaxBundle = {
      currency: (r.currency ?? parsed?.currency ?? "").trim() || null,
      gst: moneyFromRowOrParsed(r.gst, parsed?.gst ?? null),
      pst: parseBvdMoneyString(r.pst ?? ""),
      qst: moneyFromRowOrParsed(r.qst, parsed?.qst ?? null),
      hst: null,
    };

    const prev = map.get(cardKey);
    if (!prev) {
      map.set(cardKey, bundle);
      continue;
    }
    map.set(cardKey, {
      currency: bundle.currency ?? prev.currency,
      gst: bundle.gst ?? prev.gst,
      pst: bundle.pst ?? prev.pst,
      qst: bundle.qst ?? prev.qst,
      hst: prev.hst,
    });
  }

  return map;
}
