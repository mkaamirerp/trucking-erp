import type { FuelNationwideRow } from "../../api";
import {
  formatProviderMoneyAmount,
  isProviderMoneyDashLike,
} from "../fuel/fuelProviderMoneyDisplay";

const MONEY_FIELDS = new Set([
  "ex_gst_per_unit",
  "total",
  "usa_discount",
  "missed_disc",
  "oon_fees",
]);

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

function explicitCardTotalTaxSuffix(row: FuelNationwideRow): string {
  const parts: string[] = [];
  const gst = row.gst?.trim();
  if (gst) {
    parts.push(`GST ${formatProviderMoneyToken(gst.replace(/^\$/, ""))}`);
  }
  const qst = row.qst?.trim();
  if (qst && !["0", "0.00", "$0", "$0.00"].includes(qst)) {
    parts.push(`QST ${formatProviderMoneyToken(qst.replace(/^\$/, ""))}`);
  }
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

function nationwideCardTotalColumns(row: FuelNationwideRow): NationwideControlColumns {
  const type = row.control_type?.trim() || "CARD_TOTAL";
  const card = row.card_number?.trim() || "—";
  const currency = row.currency?.trim().toUpperCase() || "—";
  const label = card !== "—" && currency !== "—" ? `${card} · ${currency}` : card;
  const declared = row.declared_amount?.trim();
  const amount = declared
    ? `${formatProviderMoneyToken(declared.replace(/^\$/, ""))}${explicitCardTotalTaxSuffix(row)}`
    : "—";
  return { type, label, amount };
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
    return { type, label: labelText, amount };
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
