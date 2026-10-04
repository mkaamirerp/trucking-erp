import type { FuelBvdRow } from "../../api";
import {
  formatMoneyDisplay,
  moneyIsNonZero,
  BVD_TAX_FIELDS,
} from "./bvdCompletedBasicProjection";
import { displayCell, operationalCell, sortBvdRows } from "./bvdParsedDisplay";
import { parseBvdMoneyString } from "./bvdParsedValidation";
import type { FuelBvdSourceReconciliation } from "./bvdReconciliationStrip";

const PRODUCT_SEGMENT_COLORS: Record<string, string> = {
  TA: "#3b82f6",
  TF: "#a855f7",
  DF: "#22c55e",
  S: "#ec4899",
  Express: "#f97316",
  Manual: "#94a3b8",
  Scale: "#14b8a6",
};

const CONTROL_ROW_TYPES = new Set([
  "TRANSACTION_SUBTOTAL",
  "PAGE1_SUMMARY",
  "GRAND_TOTAL",
  "LEGEND",
  "EXPRESS_SUBTOTAL",
]);

export type BvdProductBreakdownSegment = {
  key: string;
  label: string;
  amount: number;
  amountDisplay: string;
  color: string;
};

export type BvdCompactCurrencyBlock = {
  currency: string;
  invoiceTotal: string | null;
  qtyTotal: string | null;
  discountTotal: string | null;
  expressTotal: string | null;
  expressPrincipal: string | null;
  expressFees: string | null;
};

export type BvdReviewCompactSummaryModel = {
  invoiceNumber: string;
  reconciliationLabel: string;
  reconciliationPass: boolean;
  purchaseCount: number;
  expressCount: number;
  controlCount: number;
  legendCount: number;
  cardsCount: number;
  unmappedExpressCount: number;
  taxes: Array<{ key: string; label: string; amount: string }>;
  currencyBlocks: BvdCompactCurrencyBlock[];
  productSegments: BvdProductBreakdownSegment[];
};

export function displayBvdStatementCurrency(raw: string | null | undefined): string {
  const t = (raw ?? "").trim();
  if (!t) return "—";
  if (t === "US") return "USD";
  if (t === "CN") return "CAD";
  return t;
}

function sumMoney(rows: FuelBvdRow[], field: string): number {
  let total = 0;
  for (const row of rows) {
    total += parseBvdMoneyString(operationalCell(row, field)) ?? 0;
  }
  return total;
}

function sumQty(rows: FuelBvdRow[]): number {
  let total = 0;
  for (const row of rows) {
    total += parseBvdMoneyString(operationalCell(row, "qty")) ?? 0;
  }
  return total;
}

function rowCurrency(row: FuelBvdRow): string {
  const cur = operationalCell(row, "cur").trim();
  return displayBvdStatementCurrency(cur || "—");
}

function distinctPurchaseCards(sorted: FuelBvdRow[]): number {
  const seen = new Set<string>();
  for (const row of sorted) {
    if (row.row_type !== "TRANSACTION" && row.row_type !== "TRANSACTION_SUBTOTAL") continue;
    const card = operationalCell(row, "card_number").trim();
    if (card) seen.add(card);
  }
  return seen.size;
}

function grandStatementRow(rows: FuelBvdRow[]): FuelBvdRow | undefined {
  return rows.find((r) => r.row_type === "GRAND_TOTAL" && displayCell(r, "row_label") === "Grand Total");
}

function productGrandLines(rows: FuelBvdRow[]): FuelBvdRow[] {
  return rows.filter(
    (r) =>
      r.row_type === "GRAND_TOTAL" &&
      displayCell(r, "row_label") !== "Grand Total" &&
      moneyIsNonZero(displayCell(r, "final_amount") || displayCell(r, "final_amt")),
  );
}

function buildReconciliationLabel(report: FuelBvdSourceReconciliation | null | undefined): {
  label: string;
  pass: boolean;
} {
  if (!report) {
    return { label: "—", pass: false };
  }
  const checks = report.checks ?? [];
  const passCount = checks.filter((c) => c.status === "PASS").length;
  const total = checks.length;
  const suffix = report.passed ? "PASS" : "REVIEW";
  if (total === 0) {
    return { label: report.passed ? "PASS" : "REVIEW", pass: report.passed };
  }
  return { label: `${passCount}/${total} ${suffix}`, pass: report.passed };
}

function resolveCurrencies(
  transactions: FuelBvdRow[],
  express: FuelBvdRow[],
  report: FuelBvdSourceReconciliation | null | undefined,
  grand: FuelBvdRow | undefined,
  header: FuelBvdRow | undefined,
): string[] {
  const fromReport = (report?.currencies_seen ?? []).map((c) => displayBvdStatementCurrency(c));
  if (fromReport.length > 0) {
    return [...new Set(fromReport)];
  }
  const fromRows = new Set<string>();
  for (const row of [...transactions, ...express]) {
    const c = rowCurrency(row);
    if (c !== "—") fromRows.add(c);
  }
  if (fromRows.size > 0) {
    return [...fromRows].sort();
  }
  const fallback =
    (grand && displayBvdStatementCurrency(displayCell(grand, "cur"))) ||
    (header && displayBvdStatementCurrency(displayCell(header, "cur"))) ||
    "—";
  return fallback === "—" ? [] : [fallback];
}

function filterByCurrency(rows: FuelBvdRow[], currency: string): FuelBvdRow[] {
  return rows.filter((r) => rowCurrency(r) === currency);
}

function formatQty(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function buildCurrencyBlocks(
  currencies: string[],
  transactions: FuelBvdRow[],
  express: FuelBvdRow[],
  report: FuelBvdSourceReconciliation | null | undefined,
  grand: FuelBvdRow | undefined,
): BvdCompactCurrencyBlock[] {
  const expressAll = sumMoney(express, "final_amt");
  const principalAll = sumMoney(express, "amount_cashed");
  const feesAll = sumMoney(express, "express_fee");

  if (currencies.length === 0) {
    const invoice =
      report?.provider_grand_total ??
      (grand ? formatMoneyDisplay(displayCell(grand, "final_amount") || displayCell(grand, "final_amt")) : null);
    return [
      {
        currency: "—",
        invoiceTotal: invoice,
        qtyTotal: transactions.length ? formatQty(sumQty(transactions)) : null,
        discountTotal: transactions.length ? formatMoneyDisplay(String(sumMoney(transactions, "disc_amt"))) : null,
        expressTotal: express.length ? formatMoneyDisplay(String(expressAll)) : null,
        expressPrincipal: express.length ? formatMoneyDisplay(String(principalAll)) : null,
        expressFees: express.length ? formatMoneyDisplay(String(feesAll)) : null,
      },
    ];
  }

  const multi = currencies.length > 1;
  const invoiceFromProvider = report?.provider_grand_total ?? null;

  return currencies.map((currency) => {
    const tx = filterByCurrency(transactions, currency);
    const ex = filterByCurrency(express, currency);
    const expressTotal = ex.length ? sumMoney(ex, "final_amt") : multi ? 0 : expressAll;
    const expressPrincipal = ex.length ? sumMoney(ex, "amount_cashed") : multi ? 0 : principalAll;
    const expressFees = ex.length ? sumMoney(ex, "express_fee") : multi ? 0 : feesAll;

    let invoiceTotal: string | null = null;
    if (!multi && invoiceFromProvider) {
      invoiceTotal = invoiceFromProvider;
    } else if (tx.length || ex.length) {
      const inv = sumMoney(tx, "final_amt") + (multi ? expressTotal : expressAll);
      invoiceTotal = formatMoneyDisplay(String(inv));
    } else if (!multi && grand) {
      invoiceTotal = formatMoneyDisplay(displayCell(grand, "final_amount") || displayCell(grand, "final_amt"));
    }

    const disc = tx.length ? sumMoney(tx, "disc_amt") : null;
    const qty = tx.length ? sumQty(tx) : null;

    return {
      currency,
      invoiceTotal,
      qtyTotal: qty !== null ? formatQty(qty) : null,
      discountTotal: disc !== null ? formatMoneyDisplay(String(disc)) : null,
      expressTotal:
        (multi ? ex.length : express.length)
          ? formatMoneyDisplay(String(multi ? expressTotal : expressAll))
          : null,
      expressPrincipal:
        (multi ? ex.length : express.length)
          ? formatMoneyDisplay(String(multi ? expressPrincipal : principalAll))
          : null,
      expressFees:
        (multi ? ex.length : express.length)
          ? formatMoneyDisplay(String(multi ? expressFees : feesAll))
          : null,
    };
  });
}

function buildProductSegments(rows: FuelBvdRow[]): BvdProductBreakdownSegment[] {
  const lines = productGrandLines(rows);
  const segments: BvdProductBreakdownSegment[] = [];
  for (const row of lines) {
    const key = (displayCell(row, "product") || displayCell(row, "row_label") || "other").trim();
    const amountRaw = displayCell(row, "final_amount") || displayCell(row, "final_amt");
    const amount = parseBvdMoneyString(amountRaw) ?? 0;
    if (amount <= 0) continue;
    const label = key === "Cash Advance" ? "Express" : key;
    segments.push({
      key,
      label,
      amount,
      amountDisplay: formatMoneyDisplay(amountRaw),
      color: PRODUCT_SEGMENT_COLORS[label] ?? PRODUCT_SEGMENT_COLORS[key] ?? "#64748b",
    });
  }
  return segments;
}

function nonzeroTaxLines(grand: FuelBvdRow | undefined): Array<{ key: string; label: string; amount: string }> {
  if (!grand) return [];
  const lines: Array<{ key: string; label: string; amount: string }> = [];
  for (const { field, label } of BVD_TAX_FIELDS) {
    const raw = displayCell(grand, field);
    if (moneyIsNonZero(raw)) {
      lines.push({ key: field, label, amount: formatMoneyDisplay(raw) });
    }
  }
  return lines;
}

/** Compact post-upload review summary — rows + authoritative reconciliation only. */
export function buildBvdReviewCompactSummary(
  rows: FuelBvdRow[],
  sourceReconciliation: FuelBvdSourceReconciliation | null | undefined,
): BvdReviewCompactSummaryModel {
  const sorted = sortBvdRows(rows);
  const header = sorted.find((r) => r.row_type === "HEADER");
  const transactions = sorted.filter((r) => r.row_type === "TRANSACTION");
  const express = sorted.filter((r) => r.row_type === "EXPRESS_TRANSACTION");
  const grand = grandStatementRow(sorted);
  const { label: reconciliationLabel, pass: reconciliationPass } =
    buildReconciliationLabel(sourceReconciliation);

  const controlCount = sorted.filter((r) => CONTROL_ROW_TYPES.has(r.row_type)).length;
  const legendCount = sorted.filter((r) => r.row_type === "LEGEND").length;

  const currencies = resolveCurrencies(transactions, express, sourceReconciliation, grand, header);

  return {
    invoiceNumber: header ? displayCell(header, "invoice_number") : "",
    reconciliationLabel,
    reconciliationPass,
    purchaseCount: transactions.length,
    expressCount: express.length,
    controlCount,
    legendCount,
    cardsCount: distinctPurchaseCards(sorted),
    unmappedExpressCount: express.length,
    taxes: nonzeroTaxLines(grand),
    currencyBlocks: buildCurrencyBlocks(currencies, transactions, express, sourceReconciliation, grand),
    productSegments: buildProductSegments(sorted),
  };
}
