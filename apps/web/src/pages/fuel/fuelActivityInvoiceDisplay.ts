import type { FuelActivityRow } from "./fuelActivityRow";
import {
  formatDualCurrencyInvoiceTotalLabel,
  formatProviderMoneyAmount,
} from "./fuelProviderMoneyDisplay";
import { formatBvdSourceDate } from "../fuelBvdReview/bvdUploadDuplicate";

/** Dashboard bucket for source currency (no FX). Provider codes US/CN preserved on invoice total. */
export type FuelActivityMoneyBucket = "cad" | "usd";

export function fuelActivitySourceMoneyBucket(
  currency: string | null | undefined,
): FuelActivityMoneyBucket | null {
  const c = currency?.trim().toUpperCase();
  if (!c) return null;
  if (c === "USD" || c === "US") return "usd";
  if (c === "CN" || c === "CAD") return "cad";
  return null;
}

/** Canonical processed read: multi-currency batches omit single total_amount. */
export function fuelActivityIsMultiCurrencySummary(row: FuelActivityRow): boolean {
  if (row.total_amount?.trim()) return false;
  return Boolean(row.cad_transaction_total?.trim() || row.usd_transaction_total?.trim());
}

/** Recent Activity Account/Card from completed-basic purchase card summary (not header alone). */
export function formatFuelActivityAccountCard(row: FuelActivityRow): string {
  if (row.provider === "NATIONWIDE" && row.account_code?.trim()) {
    return row.account_code.trim();
  }
  const count = row.purchase_card_count ?? 0;
  const numbers = row.purchase_card_numbers ?? [];
  if (count <= 0) return "—";
  if (count === 1) {
    const sole = numbers[0]?.trim() || row.card_number?.trim();
    return sole || "—";
  }
  return `${count} cards`;
}

/** Provider invoice payment status — not Fuel process status. */
export function fuelActivityPaymentLabel(_row: FuelActivityRow): string {
  return "Not tracked";
}

function parseProviderDay(value: string): Date | null {
  const day = value.trim().slice(0, 10);
  if (!day) return null;
  const d = new Date(`${day}T12:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function monthDay(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function monthDayYear(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** Compact statement period from header start_date / end_date. */
export function formatFuelActivityPeriod(
  periodStart: string | null | undefined,
  periodEnd: string | null | undefined,
): string {
  const start = periodStart?.trim() ? parseProviderDay(periodStart) : null;
  const end = periodEnd?.trim() ? parseProviderDay(periodEnd) : null;
  if (!start && !end) return "—";
  if (start && !end) return monthDayYear(start);
  if (!start && end) return monthDayYear(end);

  const sameYear = start!.getFullYear() === end!.getFullYear();
  const sameMonth = sameYear && start!.getMonth() === end!.getMonth();

  if (sameMonth) {
    const month = start!.toLocaleDateString("en-US", { month: "short" });
    return `${month} ${start!.getDate()}–${end!.getDate()}`;
  }
  if (sameYear) {
    return `${monthDay(start!)} – ${monthDay(end!)}`;
  }
  return `${monthDayYear(start!)} – ${monthDayYear(end!)}`;
}

export function formatFuelActivityDueDate(dueDate: string | null | undefined): string {
  if (!dueDate?.trim()) return "—";
  return formatBvdSourceDate(dueDate);
}

export function formatFuelActivityInvoiceDiscount(row: FuelActivityRow): string {
  return formatProviderMoneyAmount(row.invoice_disc_amt, { emptyAsZero: true });
}

export function formatFuelActivityCadTotal(row: FuelActivityRow): string {
  if (fuelActivityIsMultiCurrencySummary(row)) {
    return formatProviderMoneyAmount(row.cad_transaction_total, { emptyAsZero: true });
  }
  const explicit = row.cad_transaction_total?.trim();
  if (explicit) return explicit;
  const bucket = fuelActivitySourceMoneyBucket(row.currency);
  const amt = row.total_amount?.trim();
  if (!bucket || !amt) return "—";
  return bucket === "cad" ? amt : "0.00";
}

export function formatFuelActivityUsdTotal(row: FuelActivityRow): string {
  if (fuelActivityIsMultiCurrencySummary(row)) {
    return formatProviderMoneyAmount(row.usd_transaction_total, { emptyAsZero: true });
  }
  const explicit = row.usd_transaction_total?.trim();
  if (explicit) return explicit;
  const bucket = fuelActivitySourceMoneyBucket(row.currency);
  const amt = row.total_amount?.trim();
  if (!bucket || !amt) return "—";
  return bucket === "usd" ? amt : "0.00";
}

export function formatFuelActivityInvoiceTotal(row: FuelActivityRow): string {
  const total = row.total_amount?.trim();
  const currency = row.currency?.trim();
  if (total && currency) return `${total} ${currency}`;
  if (total) return total;

  if (fuelActivityIsMultiCurrencySummary(row)) {
    return formatDualCurrencyInvoiceTotalLabel(
      formatFuelActivityCadTotal(row),
      formatFuelActivityUsdTotal(row),
    );
  }

  return "—";
}
