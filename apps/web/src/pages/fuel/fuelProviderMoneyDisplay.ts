/**
 * Provider-neutral Fuel money presentation (BVD, Nationwide, future WEX, …).
 * Does not mutate source values; maps blank/PDF-zero to 0.00 per Fuel contract.
 */

export function isProviderMoneyDashLike(raw: string | null | undefined): boolean {
  if (raw === null || raw === undefined) return true;
  const t = raw.trim();
  return t === "" || t === "-" || t === "—" || t === "-$" || t === "$-" || t === "$";
}

export type FormatProviderMoneyOptions = {
  /** Blank/dash → 0.00 instead of em dash (provider zero on PDF). */
  emptyAsZero?: boolean;
};

/** Single money token for tables (activity, processing, etc.). */
export function formatProviderMoneyAmount(
  raw: string | null | undefined,
  options?: FormatProviderMoneyOptions,
): string {
  if (isProviderMoneyDashLike(raw)) {
    return options?.emptyAsZero ? "0.00" : "—";
  }
  return String(raw).trim();
}

/** Join CAD/USD bucket totals for invoice-level display (no FX). */
export function formatDualCurrencyInvoiceTotalLabel(
  cadAmount: string,
  usdAmount: string,
): string {
  const parts: string[] = [];
  if (cadAmount !== "—") parts.push(`${cadAmount} CAD`);
  if (usdAmount !== "—") parts.push(`${usdAmount} USD`);
  return parts.length ? parts.join(" · ") : "—";
}
