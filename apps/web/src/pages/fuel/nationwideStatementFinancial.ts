import type { FuelBvdRow, FuelNationwideRow, FuelNationwideSourceReconciliation } from "../../api";
import { formatMoneyDisplay } from "../fuelBvdReview/bvdCompletedBasicProjection";
import { parseBvdMoneyString } from "../fuelBvdReview/bvdParsedValidation";
import {
  type NationwideCardTaxBundle,
  normalizeNationwideCardKey,
} from "./nationwideCardTotalLine";

const MONEY_EPS = 0.005;

function formatLineMoney(n: number): string {
  return formatMoneyDisplay(String(n));
}

function isCanadianCurrency(raw: string | null | undefined): boolean {
  const c = (raw ?? "").trim().toUpperCase();
  return c === "CAD" || c === "CN";
}

/** Ex-tax extension from provider Ex-GST ($/U) × Volume — not a substitute when BVD supplies pre_tax_amt. */
export function nationwideExTaxLineAmount(
  row: Pick<FuelNationwideRow, "ex_gst_per_unit" | "volume">,
): number | null {
  const unit = parseBvdMoneyString(row.ex_gst_per_unit ?? "");
  const qty = parseBvdMoneyString(row.volume ?? "");
  if (unit === null || qty === null) return null;
  return unit * qty;
}

export type NationwideStatementTaxFields = {
  pre_tax_amt: string;
  hst: string;
  gst: string;
  pst: string;
  qst: string;
};

export type NationwideFinancialContext = {
  cardTax?: NationwideCardTaxBundle | null;
};

function attachNonZeroTaxes(
  out: Partial<NationwideStatementTaxFields>,
  taxes: {
    gst?: number | null;
    pst?: number | null;
    qst?: number | null;
    hst?: number | null;
  },
): Partial<NationwideStatementTaxFields> {
  if (taxes.gst !== null && taxes.gst !== undefined && Math.abs(taxes.gst) > MONEY_EPS) {
    out.gst = formatLineMoney(taxes.gst);
  }
  if (taxes.pst !== null && taxes.pst !== undefined && Math.abs(taxes.pst) > MONEY_EPS) {
    out.pst = formatLineMoney(taxes.pst);
  }
  if (taxes.qst !== null && taxes.qst !== undefined && Math.abs(taxes.qst) > MONEY_EPS) {
    out.qst = formatLineMoney(taxes.qst);
  }
  if (taxes.hst !== null && taxes.hst !== undefined && Math.abs(taxes.hst) > MONEY_EPS) {
    out.hst = formatLineMoney(taxes.hst);
  }
  return out;
}

/**
 * Map Nationwide purchase row → shared fuel grid money fields (BVD-shaped keys).
 * CAD: ex-tax extension when present; otherwise CARD_TOTAL GST/QST on the card.
 */
export function nationwideStatementFinancialFields(
  row: FuelNationwideRow,
  ctx?: NationwideFinancialContext,
): Partial<NationwideStatementTaxFields> {
  const total = parseBvdMoneyString(row.total ?? "");
  const currency = (row.currency?.trim() || ctx?.cardTax?.currency?.trim() || "").trim();

  const explicitGst = parseBvdMoneyString(row.gst ?? "");
  const explicitPst = parseBvdMoneyString(row.pst ?? "");
  const explicitQst = parseBvdMoneyString(row.qst ?? "");
  const cardTax = ctx?.cardTax;

  if (isCanadianCurrency(currency)) {
    const exTax = nationwideExTaxLineAmount(row);
    if (exTax !== null && total !== null) {
      const preTaxRounded = Math.round(exTax * 100) / 100;
      const pre_tax_amt = formatLineMoney(preTaxRounded);

      let gst = explicitGst;
      if (gst === null) {
        const implied = total - preTaxRounded;
        gst = Math.abs(implied) <= MONEY_EPS ? 0 : implied;
      }
      if ((gst === null || Math.abs(gst) <= MONEY_EPS) && cardTax?.gst != null) {
        gst = cardTax.gst;
      }

      const out: Partial<NationwideStatementTaxFields> = { pre_tax_amt };
      return attachNonZeroTaxes(out, {
        gst,
        pst: explicitPst ?? cardTax?.pst ?? null,
        qst: explicitQst ?? cardTax?.qst ?? null,
      });
    }

    if (total !== null && cardTax) {
      const gst = explicitGst ?? cardTax.gst;
      if (gst !== null && Math.abs(gst) > MONEY_EPS) {
        const preTaxRounded = Math.round((total - gst) * 100) / 100;
        const out: Partial<NationwideStatementTaxFields> = {
          pre_tax_amt: formatLineMoney(preTaxRounded),
        };
        return attachNonZeroTaxes(out, {
          gst,
          pst: explicitPst ?? cardTax.pst,
          qst: explicitQst ?? cardTax.qst,
        });
      }
    }
    return {};
  }

  // USD / other: Ex-GST column is final gallon price; line total is authoritative (no line tax split).
  if (total !== null) {
    return { pre_tax_amt: formatLineMoney(total) };
  }
  return {};
}

type TaxField = "gst" | "pst" | "qst" | "hst";

const TAX_FIELDS: TaxField[] = ["gst", "pst", "qst", "hst"];

function rowTaxAmount(row: FuelBvdRow, field: TaxField): number {
  const n = parseBvdMoneyString(String(row[field] ?? ""));
  return n === null ? 0 : n;
}

/** Spread CARD_TOTAL taxes onto purchase lines when line-level amounts are still zero. */
export function applyNationwideCardTaxToStatementRows(
  purchases: FuelBvdRow[],
  ledger: Map<string, NationwideCardTaxBundle>,
): FuelBvdRow[] {
  if (!ledger.size) return purchases;

  const byCard = new Map<string, FuelBvdRow[]>();
  for (const row of purchases) {
    const key = normalizeNationwideCardKey(row.card_number);
    if (!key) continue;
    const list = byCard.get(key) ?? [];
    list.push(row);
    byCard.set(key, list);
  }

  const patch = new Map<number, Partial<FuelBvdRow>>();

  for (const [cardKey, lines] of byCard) {
    const bundle = ledger.get(cardKey);
    if (!bundle) continue;

    for (const field of TAX_FIELDS) {
      const cardAmount = bundle[field];
      if (cardAmount === null || cardAmount === undefined || Math.abs(cardAmount) <= MONEY_EPS) {
        continue;
      }

      const lineSum = lines.reduce((s, l) => s + rowTaxAmount(l, field), 0);
      if (Math.abs(lineSum - cardAmount) <= MONEY_EPS) continue;

      const needy = lines.filter((l) => Math.abs(rowTaxAmount(l, field)) <= MONEY_EPS);
      if (!needy.length) continue;

      const weightOf = (l: FuelBvdRow): number => {
        const finalAmt = parseBvdMoneyString(l.final_amt ?? "");
        if (finalAmt !== null && finalAmt > 0) return finalAmt;
        const qty = parseBvdMoneyString(l.qty ?? "");
        return qty !== null && qty > 0 ? qty : 1;
      };

      const weights = needy.map(weightOf);
      const weightTotal = weights.reduce((a, b) => a + b, 0) || needy.length;

      needy.forEach((line, idx) => {
        const share =
          needy.length === 1
            ? cardAmount
            : Math.round((cardAmount * (weights[idx] / weightTotal)) * 100) / 100;
        const existing = patch.get(line.id) ?? {};
        patch.set(line.id, {
          ...existing,
          [field]: formatLineMoney(share),
        });

        if (field === "gst") {
          const total = parseBvdMoneyString(line.final_amt ?? "");
          if (total !== null) {
            const preTax = Math.round((total - share) * 100) / 100;
            patch.set(line.id, {
              ...patch.get(line.id),
              pre_tax_amt: formatLineMoney(preTax),
            });
          }
        }
      });
    }

    const currency = bundle.currency?.trim();
    if (currency) {
      for (const line of lines) {
        if ((line.cur ?? "").trim()) continue;
        const existing = patch.get(line.id) ?? {};
        patch.set(line.id, { ...existing, cur: currency });
      }
    }
  }

  if (!patch.size) return purchases;
  return purchases.map((row) => ({ ...row, ...patch.get(row.id) }));
}

function isCanadianStatementRow(row: FuelBvdRow): boolean {
  const c = (row.cur ?? "").trim().toUpperCase();
  return c === "CAD" || c === "CN";
}

function allocateInvoiceCadTaxField(
  purchases: FuelBvdRow[],
  field: TaxField,
  invoiceTotalRaw: string | null | undefined,
): FuelBvdRow[] {
  const invoiceTotal = parseBvdMoneyString(invoiceTotalRaw ?? "");
  if (invoiceTotal === null || Math.abs(invoiceTotal) <= MONEY_EPS) return purchases;

  const cadLines = purchases.filter(isCanadianStatementRow);
  const needy = cadLines.filter((l) => Math.abs(rowTaxAmount(l, field)) <= MONEY_EPS);
  if (!needy.length) return purchases;

  const existingSum = cadLines.reduce((s, l) => s + rowTaxAmount(l, field), 0);
  if (Math.abs(existingSum - invoiceTotal) <= MONEY_EPS) return purchases;

  const weightOf = (l: FuelBvdRow): number => {
    const finalAmt = parseBvdMoneyString(l.final_amt ?? "");
    if (finalAmt !== null && finalAmt > 0) return finalAmt;
    return 1;
  };
  const weights = needy.map(weightOf);
  const weightTotal = weights.reduce((a, b) => a + b, 0) || needy.length;

  const patch = new Map<number, Partial<FuelBvdRow>>();
  needy.forEach((line, idx) => {
    const share =
      needy.length === 1
        ? invoiceTotal
        : Math.round((invoiceTotal * (weights[idx] / weightTotal)) * 100) / 100;
    patch.set(line.id, { ...patch.get(line.id), [field]: formatLineMoney(share) });
    if (field === "gst" || field === "pst" || field === "hst") {
      const total = parseBvdMoneyString(line.final_amt ?? "");
      if (total !== null) {
        const taxSoFar =
          TAX_FIELDS.reduce((s, f) => {
            const fromPatch = patch.get(line.id)?.[f];
            const n = fromPatch
              ? parseBvdMoneyString(fromPatch)
              : rowTaxAmount(line, f);
            return s + (n ?? 0);
          }, 0);
        const preTax = Math.round((total - taxSoFar) * 100) / 100;
        patch.set(line.id, { ...patch.get(line.id), pre_tax_amt: formatLineMoney(preTax) });
      }
    }
  });

  return purchases.map((row) => ({ ...row, ...patch.get(row.id) }));
}

/** Invoice-level CAD GST/PST controls when CARD_TOTAL rows did not hydrate line taxes. */
export function applyNationwideReconciliationCadTax(
  purchases: FuelBvdRow[],
  recon: FuelNationwideSourceReconciliation | null | undefined,
): FuelBvdRow[] {
  if (!recon) return purchases;
  let rows = allocateInvoiceCadTaxField(purchases, "gst", recon.cad_gst);
  rows = allocateInvoiceCadTaxField(rows, "pst", recon.cad_pst);
  return rows;
}
