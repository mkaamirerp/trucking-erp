/**
 * Duplicate candidate review — ``shared/global_booking_broker_duplicate_review_reason_codes.json``.
 */
import spec from "@repo-shared/global_booking_broker_duplicate_review_reason_codes.json";

type SpecT = {
  schema_version: number;
  dismiss: { write: string[] };
  acknowledge: { write: string[] };
  operator_hint: Record<string, string>;
};

const data = spec as SpecT;

export const DUPLICATE_REVIEW_REASON_SCHEMA_VERSION = data.schema_version;

export type DupReviewOption = { code: string; label: string };

function opts(codes: string[]): DupReviewOption[] {
  return codes.map((code) => ({ code, label: data.operator_hint[code] ?? code }));
}

export const DUPLICATE_REVIEW_DISMISS_OPTIONS = opts(data.dismiss.write);

export const DUPLICATE_REVIEW_ACK_OPTIONS = opts(data.acknowledge.write);

export function duplicateReviewReasonHint(code: string | null | undefined): string | null {
  if (code == null || code === "") return null;
  const h = data.operator_hint[code];
  return h !== undefined ? h : null;
}
