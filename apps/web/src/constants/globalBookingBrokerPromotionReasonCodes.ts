/**
 * Global booking broker promotion — aligned with ``shared/global_booking_broker_promotion_reason_codes.json``.
 * Write sets + operator_hint drive dropdowns; optional note is supplemental only.
 */
import spec from "@repo-shared/global_booking_broker_promotion_reason_codes.json";

type ReasonSpec = {
  schema_version: number;
  approve: { write: string[] };
  reject: { write: string[] };
  reopen: { write: string[] };
  operator_hint: Record<string, string>;
};

const data = spec as ReasonSpec;

export const GLOBAL_BROKER_PROMOTION_REASON_SCHEMA_VERSION = data.schema_version;

export type GlobalBrokerPromotionReasonOption = { code: string; label: string };

function optionsForCodes(codes: string[]): GlobalBrokerPromotionReasonOption[] {
  return codes.map((code) => ({
    code,
    label: data.operator_hint[code] ?? code,
  }));
}

/** Allowed reasons when moving to ``nextStatus`` from ``prevStatus`` (same rules as API). */
export function globalBrokerPromotionReasonOptions(prevStatus: string, nextStatus: string): GlobalBrokerPromotionReasonOption[] {
  const p = prevStatus.toLowerCase();
  const n = nextStatus.toLowerCase();
  if (n === "approved" && (p === "pending" || p === "rejected")) {
    return optionsForCodes(data.approve.write);
  }
  if (n === "rejected" && (p === "pending" || p === "approved")) {
    return optionsForCodes(data.reject.write);
  }
  if (n === "pending" && (p === "approved" || p === "rejected")) {
    return optionsForCodes(data.reopen.write);
  }
  return [];
}

export function globalBrokerPromotionTargets(prevStatus: string): { value: "approved" | "rejected" | "pending"; label: string }[] {
  const p = prevStatus.toLowerCase();
  if (p === "pending") {
    return [
      { value: "approved", label: "Approve" },
      { value: "rejected", label: "Reject" },
    ];
  }
  if (p === "approved") {
    return [
      { value: "rejected", label: "Reject" },
      { value: "pending", label: "Return to queue" },
    ];
  }
  if (p === "rejected") {
    return [
      { value: "approved", label: "Approve" },
      { value: "pending", label: "Return to queue" },
    ];
  }
  return [];
}

export function globalBrokerPromotionReasonHint(code: string | null | undefined): string | null {
  if (code == null || code === "") return null;
  const h = data.operator_hint[code];
  return h !== undefined ? h : null;
}
