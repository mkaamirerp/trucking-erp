/**
 * Intake review reason codes — aligned with ``shared/email_intake_review_reason_codes.json``.
 * Write sets + operator_hint drive dropdowns; event labels stay UI-local.
 */
import spec from "@repo-shared/email_intake_review_reason_codes.json";

type ReasonSpec = {
  schema_version: number;
  resolve: { write: string[] };
  dismiss: { write: string[] };
  reopen: { write: string[] };
  operator_hint: Record<string, string>;
};

const data = spec as ReasonSpec;

export const INTAKE_REVIEW_REASON_SCHEMA_VERSION = data.schema_version;

export type IntakeReviewReasonOption = { code: string; label: string };

function optionsForWriteCodes(codes: string[]): IntakeReviewReasonOption[] {
  return codes.map((code) => ({
    code,
    label: data.operator_hint[code] ?? code,
  }));
}

/** POST /intake-review/resolve — reason_code choices (labels from JSON, never raw in UI). */
export const INTAKE_REVIEW_RESOLVE_OPTIONS = optionsForWriteCodes(data.resolve.write);

/** POST /intake-review/dismiss */
export const INTAKE_REVIEW_DISMISS_OPTIONS = optionsForWriteCodes(data.dismiss.write);

/** POST /intake-review/reopen */
export const INTAKE_REVIEW_REOPEN_OPTIONS = optionsForWriteCodes(data.reopen.write);

/** Short operator-facing hint for Activity / tooltips; null if legacy/unmapped. */
export function intakeReviewReasonOperatorHint(code: string | null | undefined): string | null {
  if (code == null || code === "") return null;
  const h = data.operator_hint[code];
  return h !== undefined ? h : null;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  review_opened: "Opened",
  detail_synced: "Details updated",
  reopened: "Reopened (sync)",
  reopened_manual: "Reopened",
  claimed: "Claimed",
  resolved: "Resolved",
  dismissed: "Dismissed",
  duplicate_link_prior: "Link: prior load",
  auto_resolved_thread_linked_load: "Closed: load linked",
  duplicate_confirmed: "Confirmed duplicate",
};

export function intakeReviewEventTypeLabel(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] ?? "Update";
}
