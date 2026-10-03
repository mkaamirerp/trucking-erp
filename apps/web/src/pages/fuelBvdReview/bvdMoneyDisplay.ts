import { formatMoneyDisplay } from "./bvdCompletedBasicProjection";
import { parseBvdMoneyString } from "./bvdParsedValidation";

function isDashLikeMoney(raw: string): boolean {
  const t = raw.trim();
  return t === "" || t === "-" || t === "—" || t === "-$" || t === "$-" || t === "$";
}

/** BVD provider money columns: PDF zero often stored blank — show 0.00 (FUEL_BVD_IMPLEMENTATION_1). */
export const BVD_PROVIDER_MONEY_FIELDS = new Set([
  "retail",
  "billed",
  "pre_tax_amt",
  "hst",
  "gst",
  "pst",
  "qst",
  "disc_rate",
  "disc_amt",
  "final_amt",
  "final_amount",
  "amount_cashed",
  "express_fee",
]);

export function isBvdProviderMoneyField(field: string): boolean {
  return BVD_PROVIDER_MONEY_FIELDS.has(field);
}

/** Parser baseline for review compare (blank money → 0.00). */
export function bvdParserMoneyBaseline(field: string, extracted: string): string {
  const t = extracted.trim();
  if (isBvdProviderMoneyField(field) && !t) {
    return "0.00";
  }
  return t;
}

/** Compact table money cell — known zero → 0.00; missing → — (or 0.00 when emptyAsZero); else formatted source. */
export function formatBvdTxnCompactMoney(
  raw: string,
  options?: { emptyAsZero?: boolean },
): string {
  const t = raw.trim();
  if (isDashLikeMoney(t)) {
    return options?.emptyAsZero ? "0.00" : "—";
  }
  const formatted = formatMoneyDisplay(t);
  if (formatted) return formatted;
  const n = parseBvdMoneyString(t);
  if (n !== null) {
    return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return t;
}

export function formatBvdProviderMoneyField(raw: string): string {
  return formatBvdTxnCompactMoney(raw, { emptyAsZero: true });
}
