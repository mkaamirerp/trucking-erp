import { reviewStatusLabel } from "../fuelBvdReviewLabels";

export type FuelBvdDuplicateDetail = {
  code: string;
  message: string;
  existing_import_id: string;
  existing_status?: string;
  invoice_number?: string;
  invoice_date?: string;
  start_date?: string;
  end_date?: string;
  matched_on?: string[];
};

export function parseFuelBvdDuplicateDetail(err: unknown): FuelBvdDuplicateDetail | null {
  if (!(err instanceof Error) || !err.message.trim().startsWith("{")) {
    return null;
  }
  try {
    const body = JSON.parse(err.message) as { detail?: unknown };
    const d = body.detail;
    if (!d || typeof d !== "object" || Array.isArray(d)) {
      return null;
    }
    const rec = d as Record<string, unknown>;
    const code = typeof rec.code === "string" ? rec.code : "";
    if (
      !code.startsWith("FUEL_DUPLICATE") &&
      code !== "FUEL_POSSIBLE_REVISION" &&
      code !== "FUEL_TRANSACTION_OVERLAP"
    ) {
      return null;
    }
    const existing = rec.existing_import_id;
    if (typeof existing !== "string" || !existing) {
      return null;
    }
    return {
      code,
      message: typeof rec.message === "string" ? rec.message : "This source was already uploaded.",
      existing_import_id: existing,
      existing_status: typeof rec.existing_status === "string" ? rec.existing_status : undefined,
      invoice_number: typeof rec.invoice_number === "string" ? rec.invoice_number : undefined,
      invoice_date: typeof rec.invoice_date === "string" ? rec.invoice_date : undefined,
      start_date: typeof rec.start_date === "string" ? rec.start_date : undefined,
      end_date: typeof rec.end_date === "string" ? rec.end_date : undefined,
      matched_on: Array.isArray(rec.matched_on) ? rec.matched_on.map(String) : undefined,
    };
  } catch {
    return null;
  }
}

/** Display date portion from BVD TEXT datetime fields. */
export function formatBvdSourceDate(value: string | undefined): string {
  if (!value?.trim()) {
    return "—";
  }
  const day = value.trim().slice(0, 10);
  const parsed = new Date(`${day}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function duplicateStatusLabel(status: string | undefined): string {
  return reviewStatusLabel(status);
}
