import type { FuelBvdRow } from "../../api";
import { parseBvdMoneyString } from "./bvdParsedValidation";

export const BVD_PROVIDER_CODE = "BVD";
export const BVD_REVIEW_COMPLETE = "SOURCE_REVIEWED";

export const BVD_TAX_FIELDS: { field: string; label: string }[] = [
  { field: "hst", label: "HST" },
  { field: "gst", label: "GST" },
  { field: "pst", label: "PST" },
  { field: "qst", label: "QST" },
];

const CATEGORY_LABEL_OVERRIDES: Record<string, string> = {
  TA: "Fuel / TA",
  DF: "DEF",
  TF: "Trailer",
  Manual: "Manual",
  Express: "Express",
  Scale: "Scale",
  "Cash Advance": "Cash Advance",
  Additive: "Additive",
  Oil: "Oil",
  Lubricant: "Lubricant",
};

export type BvdCompletedBasicLine = {
  key: string;
  label: string;
  amount: string;
  linkKind?: "category" | "tax" | "unit";
};

export type BvdCompletedBasicView = {
  provider: string;
  importId: string;
  invoiceNumber: string;
  reviewStatus: string;
  readOnly: boolean;
  processedAt: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  cardNumber: string | null;
  unitCount: number;
  unitNumbers: string[];
  totalAmount: string;
  currency: string | null;
  categories: BvdCompletedBasicLine[];
  taxes: BvdCompletedBasicLine[];
};

export function moneyIsNonZero(raw: string | null | undefined): boolean {
  const n = parseBvdMoneyString(raw ?? "");
  return n !== null && Math.abs(n) > 0.000_001;
}

export function formatMoneyDisplay(raw: string | null | undefined): string {
  const n = parseBvdMoneyString(raw ?? "");
  if (n === null) return "";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function cell(row: FuelBvdRow, field: string): string {
  const v = row[field as keyof FuelBvdRow];
  if (v === null || v === undefined) return "";
  return String(v);
}

function categoryLabel(row: FuelBvdRow): string {
  const label = (cell(row, "row_label") || cell(row, "product")).trim();
  if (!label) return "Category";
  return CATEGORY_LABEL_OVERRIDES[label] ?? label;
}

function categoryAmount(row: FuelBvdRow): string {
  return formatMoneyDisplay(cell(row, "final_amount") || cell(row, "final_amt"));
}

function distinctBilledUnits(rows: FuelBvdRow[]): string[] {
  const units: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    if (row.row_type !== "TRANSACTION") continue;
    const unit = cell(row, "unit_number").trim();
    if (!unit || seen.has(unit)) continue;
    seen.add(unit);
    units.push(unit);
  }
  return units;
}

function grandTotalStatementRow(rows: FuelBvdRow[]): FuelBvdRow | undefined {
  return rows.find((r) => r.row_type === "GRAND_TOTAL" && cell(r, "row_label") === "Grand Total");
}

function nonzeroTaxLines(source: FuelBvdRow | undefined): BvdCompletedBasicLine[] {
  if (!source) return [];
  const lines: BvdCompletedBasicLine[] = [];
  for (const { field, label } of BVD_TAX_FIELDS) {
    const raw = cell(source, field);
    if (moneyIsNonZero(raw)) {
      lines.push({ key: field, label, amount: formatMoneyDisplay(raw), linkKind: "tax" });
    }
  }
  return lines;
}

function nonzeroCategoryLines(rows: FuelBvdRow[]): BvdCompletedBasicLine[] {
  const lines: BvdCompletedBasicLine[] = [];
  for (const row of rows) {
    if (row.row_type !== "GRAND_TOTAL") continue;
    if (cell(row, "row_label") === "Grand Total") continue;
    const amountRaw = cell(row, "final_amount") || cell(row, "final_amt");
    if (!moneyIsNonZero(amountRaw)) continue;
    const key = (cell(row, "product") || cell(row, "row_label") || "category").trim();
    lines.push({
      key,
      label: categoryLabel(row),
      amount: categoryAmount(row),
      linkKind: "category",
    });
  }
  return lines;
}

function processedAt(rows: FuelBvdRow[]): string | null {
  let best: string | null = null;
  for (const row of rows) {
    const reviewed = row.reviewed_at;
    if (typeof reviewed === "string" && reviewed) {
      if (!best || reviewed > best) best = reviewed;
    }
  }
  return best;
}

/** Operational projection for completed Fuel history (hides zero-value noise). */
export function buildBvdCompletedBasicView(rows: FuelBvdRow[], importId: string): BvdCompletedBasicView {
  const header = rows.find((r) => r.row_type === "HEADER");
  const status = rows.find((r) => r.review_status === BVD_REVIEW_COMPLETE)?.review_status
    ?? header?.review_status
    ?? "PENDING";
  const grand = grandTotalStatementRow(rows);
  const units = distinctBilledUnits(rows);

  const totalRaw = grand ? cell(grand, "final_amount") || cell(grand, "final_amt") : "";
  const currency = (grand && cell(grand, "cur")) || (header && cell(header, "cur")) || null;

  return {
    provider: BVD_PROVIDER_CODE,
    importId,
    invoiceNumber: header ? cell(header, "invoice_number") || "—" : "—",
    reviewStatus: status,
    readOnly: status === BVD_REVIEW_COMPLETE,
    processedAt: processedAt(rows),
    periodStart: header ? cell(header, "start_date") || null : null,
    periodEnd: header ? cell(header, "end_date") || null : null,
    cardNumber: header ? cell(header, "card_number") || null : null,
    unitCount: units.length,
    unitNumbers: units,
    totalAmount: formatMoneyDisplay(totalRaw),
    currency,
    categories: nonzeroCategoryLines(rows),
    taxes: nonzeroTaxLines(grand),
  };
}
