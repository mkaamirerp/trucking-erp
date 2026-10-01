import type { FuelNationwideRow } from "../../api";

const MONEY_FIELDS = new Set([
  "ex_gst_per_unit",
  "total",
  "usa_discount",
  "missed_disc",
  "oon_fees",
]);

function isDashLike(s: string): boolean {
  const t = s.trim();
  return t === "" || t === "-" || t === "—" || t === "-$" || t === "$-" || t === "$";
}

function parseMoneyNumber(s: string): number | null {
  const cleaned = s.replace(/[$,\s]/g, "");
  if (cleaned === "" || cleaned === "-") return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/** Presentation-only formatting; does not mutate source values. */
export function formatNationwideCell(field: string, raw: unknown): string {
  if (raw == null) return "—";
  const s = String(raw).trim();
  if (s === "") return "—";

  if (field === "oon_fees" || MONEY_FIELDS.has(field)) {
    if (isDashLike(s)) return "—";
    const n = parseMoneyNumber(s);
    if (n !== null && n === 0) return "0.00";
    if (field === "oon_fees" && s === "-$") return "—";
    return s;
  }

  return s;
}

export function nationwideRowCell(row: FuelNationwideRow, field: string): string {
  return formatNationwideCell(field, (row as Record<string, unknown>)[field]);
}

export type NationwideControlColumns = {
  type: string;
  label: string;
  amount: string;
};

const DOLLAR_AMOUNTS_RE = /\$([\d,]+\.\d{2})/g;

function extractDollarAmounts(line: string): string[] {
  const matches = [...line.matchAll(DOLLAR_AMOUNTS_RE)].map((m) => m[1]);
  return matches;
}

function stripMoneyCommas(amount: string): string {
  return amount.replace(/,/g, "").trim();
}

function formatProviderMoneyToken(raw: string): string {
  const cleaned = stripMoneyCommas(raw);
  if (!cleaned) return "—";
  if (/^\d+\.\d{2}$/.test(cleaned)) return cleaned;
  if (/^\d+\.\d$/.test(cleaned)) return `${cleaned}0`;
  return cleaned;
}

function taxSuffixFromRow(row: FuelNationwideRow, raw: string): string {
  const parts: string[] = [];
  const gst = row.gst?.trim() || "";
  const qst = (row as { qst?: string | null }).qst?.trim() || "";
  if (gst) {
    parts.push(`GST ${formatProviderMoneyToken(gst.replace(/^\$/, ""))}`);
  } else {
    const gstMatch = raw.match(/\bGST\s*\$?([\d,]+\.?\d*)/i);
    if (gstMatch) {
      parts.push(`GST ${formatProviderMoneyToken(gstMatch[1])}`);
    }
  }
  if (qst && qst !== "0" && qst !== "$0" && qst !== "$0.00") {
    parts.push(`QST ${formatProviderMoneyToken(qst.replace(/^\$/, ""))}`);
  } else {
    const qstMatch = raw.match(/\bQST\s*\$?([\d,]+\.?\d*)/i);
    if (qstMatch && qstMatch[1] !== "0") {
      parts.push(`QST ${formatProviderMoneyToken(qstMatch[1])}`);
    }
  }
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

function nationwideCardTotalColumns(row: FuelNationwideRow): NationwideControlColumns {
  const type = row.control_type?.trim() || "CARD_TOTAL";
  const raw = row.control_line_raw?.trim() || "";
  const card = row.card_number?.trim() || raw.split(/\s+/)[0] || "—";
  const hasGstInLine = /\bGST\b/i.test(raw);
  const currency = (row.currency?.trim() || (hasGstInLine ? "CAD" : "USD")).toUpperCase();
  const label = `${card} · ${currency}`;

  const declared = row.declared_amount?.trim();
  if (declared) {
    const amount = `${formatNationwideCell("declared_amount", declared)}${taxSuffixFromRow(row, raw)}`;
    return { type, label, amount };
  }

  const dollarAmounts = extractDollarAmounts(raw);
  if (hasGstInLine && dollarAmounts.length > 0) {
    const subtotal = dollarAmounts.reduce((best, cur) => {
      const bestN = Number(stripMoneyCommas(best));
      const curN = Number(stripMoneyCommas(cur));
      return curN > bestN ? cur : best;
    });
    const amount = `${formatProviderMoneyToken(subtotal)}${taxSuffixFromRow(row, raw)}`;
    return { type, label, amount };
  }

  if (dollarAmounts.length > 0) {
    return { type, label, amount: formatProviderMoneyToken(dollarAmounts[0]) };
  }

  return { type, label, amount: "—" };
}

export function nationwideControlColumns(row: FuelNationwideRow): NationwideControlColumns {
  const type = row.control_type?.trim() || "CONTROL";
  if (type === "CARD_TOTAL") {
    return nationwideCardTotalColumns(row);
  }

  const labelText = row.row_label?.trim() || "";
  const amountRaw = row.declared_amount?.trim() || "";
  const amount = amountRaw ? formatNationwideCell("declared_amount", amountRaw) : "—";

  if (labelText && labelText !== type) {
    const tax = row.gst?.trim() || row.pst?.trim() || "";
    const withTax =
      tax && amount !== "—" ? `${amount}${taxSuffixFromRow(row, row.control_line_raw || "")}` : amount;
    return { type, label: labelText, amount: withTax };
  }

  const raw = row.control_line_raw?.trim();
  if (raw) {
    if (amountRaw && raw.includes(amountRaw)) {
      const stripped = raw.replace(amountRaw, "").trim();
      return { type, label: stripped || raw, amount };
    }
    return { type, label: raw, amount };
  }

  return { type, label: "—", amount };
}
