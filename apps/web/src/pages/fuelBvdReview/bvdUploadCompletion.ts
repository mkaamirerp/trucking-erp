import { OPS } from "../../routes";

export const FUEL_PROCESSED_PARAM = "fuelProcessed";
export const FUEL_PROCESSED_INVOICE_PARAM = "invoice";

/** Post-Process return target — Fuel home (not a separate history step). */
export function buildFuelProcessedReturnPath(invoiceNumber?: string | null): string {
  const q = new URLSearchParams({ [FUEL_PROCESSED_PARAM]: "1" });
  if (invoiceNumber?.trim()) {
    q.set(FUEL_PROCESSED_INVOICE_PARAM, invoiceNumber.trim());
  }
  return `${OPS.FUEL}?${q.toString()}`;
}

/** @deprecated use buildFuelProcessedReturnPath */
export function buildBvdUploadCompletedPath(invoiceNumber?: string | null): string {
  return buildFuelProcessedReturnPath(invoiceNumber);
}

export function readFuelProcessedReturn(search: string): { invoiceNumber?: string } | null {
  const params = new URLSearchParams(search);
  if (params.get(FUEL_PROCESSED_PARAM) !== "1") {
    return null;
  }
  const invoice = params.get(FUEL_PROCESSED_INVOICE_PARAM);
  return invoice ? { invoiceNumber: invoice } : {};
}
