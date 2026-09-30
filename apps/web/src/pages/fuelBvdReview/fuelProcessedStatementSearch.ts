import type { FuelBvdRow, FuelCanonicalTransaction } from "../../api";
import { bvdProductDisplayLabel } from "./bvdProductDisplay";
import { operationalCell } from "./bvdParsedDisplay";
import { parseBvdMoneyString } from "./bvdParsedValidation";
import {
  parseBvdStatementTransactionDate,
  type DatePeriodSelection,
  transactionDateInPeriod,
} from "./fuelProcessedStatementDateFilter";

export type ProcessedStatementSearchContext = {
  headerCardNumber?: string;
  /** fuel_bvd.id → canonical classification / reason enrichment */
  canonicalByRowId?: Map<number, FuelCanonicalTransaction>;
};

function normQuery(q: string): string {
  return q.trim().toLowerCase();
}

function pushToken(parts: string[], raw: string) {
  const t = raw.trim();
  if (t) parts.push(t);
}

function moneyTokens(raw: string): string[] {
  const t = raw.trim();
  if (!t) return [];
  const tokens = [t, t.replace(/,/g, "")];
  const n = parseBvdMoneyString(t);
  if (n !== null) {
    tokens.push(n.toFixed(2));
    tokens.push(String(n));
  }
  return tokens;
}

function canonicalForRow(
  row: FuelBvdRow,
  ctx: ProcessedStatementSearchContext,
): FuelCanonicalTransaction | undefined {
  const map = ctx.canonicalByRowId;
  if (!map) return undefined;
  return map.get(row.id);
}

/** Provider-neutral search haystack for one statement row (accepted/effective values). */
export function buildProcessedStatementSearchHaystack(
  row: FuelBvdRow,
  ctx: ProcessedStatementSearchContext,
): string {
  const parts: string[] = [];
  const canon = canonicalForRow(row, ctx);

  pushToken(parts, operationalCell(row, "unit_number"));
  pushToken(parts, operationalCell(row, "express_tractor"));
  pushToken(parts, operationalCell(row, "driver_name"));
  pushToken(parts, operationalCell(row, "card_number"));
  if (ctx.headerCardNumber) pushToken(parts, ctx.headerCardNumber);
  pushToken(parts, operationalCell(row, "auth_code"));
  pushToken(parts, operationalCell(row, "express_code"));
  pushToken(parts, operationalCell(row, "site_number"));
  pushToken(parts, operationalCell(row, "prod"));
  pushToken(parts, bvdProductDisplayLabel(operationalCell(row, "prod")));
  pushToken(parts, operationalCell(row, "product"));
  pushToken(parts, operationalCell(row, "row_label"));
  pushToken(parts, operationalCell(row, "legend_product_name"));
  pushToken(parts, operationalCell(row, "payee_raw"));
  pushToken(parts, operationalCell(row, "notes_raw"));

  if (canon?.classification) pushToken(parts, canon.classification);
  if (canon?.provider_reason_raw) pushToken(parts, canon.provider_reason_raw);
  if (canon?.provider_transaction_identity) pushToken(parts, canon.provider_transaction_identity);
  if (canon?.product_code_raw) pushToken(parts, canon.product_code_raw);

  for (const field of ["final_amt", "final_amount", "amount_cashed", "pre_tax_amt", "qty", "express_fee"]) {
    for (const tok of moneyTokens(operationalCell(row, field))) {
      pushToken(parts, tok);
    }
  }
  if (canon?.total_amount != null) {
    for (const tok of moneyTokens(String(canon.total_amount))) pushToken(parts, tok);
  }

  const txnDate = operationalCell(row, "transaction_date");
  pushToken(parts, txnDate);
  const parsed = parseBvdStatementTransactionDate(txnDate);
  if (parsed) {
    pushToken(parts, parsed.toISOString().slice(0, 10));
    pushToken(parts, parsed.toLocaleDateString("en-CA"));
  }

  return parts.join(" ").toLowerCase();
}

export function processedStatementRowMatchesSearch(
  row: FuelBvdRow,
  query: string,
  ctx: ProcessedStatementSearchContext,
): boolean {
  const q = normQuery(query);
  if (!q) return true;
  const hay = buildProcessedStatementSearchHaystack(row, ctx);
  return hay.includes(q);
}

export function processedStatementRowMatchesDatePeriod(
  row: FuelBvdRow,
  period: DatePeriodSelection,
): boolean {
  const txnDate = parseBvdStatementTransactionDate(operationalCell(row, "transaction_date"));
  return transactionDateInPeriod(txnDate, period);
}

export function filterProcessedStatementRows(
  rows: FuelBvdRow[],
  query: string,
  period: DatePeriodSelection,
  ctx: ProcessedStatementSearchContext,
): FuelBvdRow[] {
  return rows.filter(
    (row) =>
      processedStatementRowMatchesDatePeriod(row, period) &&
      processedStatementRowMatchesSearch(row, query, ctx),
  );
}

/** Map fuel_bvd row id → canonical txn (auth_code / express identity). */
export function buildCanonicalByBvdRowId(
  bvdRows: FuelBvdRow[],
  canonical: FuelCanonicalTransaction[],
): Map<number, FuelCanonicalTransaction> {
  const byIdentity = new Map<string, FuelCanonicalTransaction>();
  for (const c of canonical) {
    const id = (c.provider_transaction_identity ?? "").trim();
    if (id) byIdentity.set(id.toLowerCase(), c);
  }
  const out = new Map<number, FuelCanonicalTransaction>();
  for (const row of bvdRows) {
    const auth = operationalCell(row, "auth_code").trim().toLowerCase();
    if (auth && byIdentity.has(auth)) {
      out.set(row.id, byIdentity.get(auth)!);
      continue;
    }
    const express = operationalCell(row, "express_code").trim().toLowerCase();
    if (express && byIdentity.has(express)) {
      out.set(row.id, byIdentity.get(express)!);
    }
  }
  return out;
}

export function isProcessedStatementSearchableRow(row: FuelBvdRow): boolean {
  return row.row_type === "TRANSACTION" || row.row_type === "EXPRESS_TRANSACTION";
}
