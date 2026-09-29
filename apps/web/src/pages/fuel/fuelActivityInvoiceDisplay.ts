import type { FuelBvdCompletedBasic } from "../../api";
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

/** Recent Activity Account/Card from completed-basic purchase card summary (not header alone). */
export function formatFuelActivityAccountCard(row: FuelBvdCompletedBasic): string {
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
export function fuelActivityPaymentLabel(_row: FuelBvdCompletedBasic): string {
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

export function formatFuelActivityInvoiceDiscount(row: FuelBvdCompletedBasic): string {
  if (row.invoice_disc_amt === undefined || row.invoice_disc_amt === null) return "—";
  const amt = row.invoice_disc_amt.trim();
  if (!amt) return "—";
  return amt;
}

export function formatFuelActivityCadTotal(row: FuelBvdCompletedBasic): string {
  const bucket = fuelActivitySourceMoneyBucket(row.currency);
  const amt = row.total_amount?.trim();
  if (bucket !== "cad" || !amt) return "—";
  return amt;
}

export function formatFuelActivityUsdTotal(row: FuelBvdCompletedBasic): string {
  const bucket = fuelActivitySourceMoneyBucket(row.currency);
  const amt = row.total_amount?.trim();
  if (bucket !== "usd" || !amt) return "—";
  return amt;
}

export function formatFuelActivityInvoiceTotal(row: FuelBvdCompletedBasic): string {
  const total = row.total_amount?.trim();
  if (!total) return "—";
  if (row.currency?.trim()) return `${total} ${row.currency.trim()}`;
  return total;
}
