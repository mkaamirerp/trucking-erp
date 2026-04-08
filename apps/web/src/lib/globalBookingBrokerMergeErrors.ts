/**
 * Maps backend merge preview / execute `detail` strings to operator-facing copy.
 */

const DIRECT: Record<string, string> = {
  merge_self_not_allowed: "You picked the same record as both source and survivor. Choose one record to keep and one to retire.",
  global_booking_broker_merge_source_blocked_already_loser:
    "The record you marked as “retire” was already merged into another broker. Use the survivor from that merge, or fix data before retrying.",
  global_booking_broker_merge_survivor_blocked_already_loser:
    "The record you marked as “keep” was already merged into another broker. It cannot absorb a merge. Pick a different survivor.",
  merge_preview_not_eligible:
    "This pair can’t be merged right now (blocked or conflicting identifiers). Review the preview messages or update broker data, then run preview again.",
  merge_preview_stale:
    "Broker data changed since this preview. Close the wizard and run preview again from the duplicate pair.",
  merge_preview_hash_mismatch:
    "Preview token didn’t match. Run preview again, then execute without changing brokers in between.",
  merge_preview_not_found: "Saved preview not found. Run preview again.",
  merge_preview_payload_mismatch: "Preview data doesn’t match these brokers. Run preview again.",
  merge_preview_row_mismatch: "Preview row doesn’t match these brokers. Run preview again.",
  merge_preview_dup_mismatch: "Duplicate-candidate link doesn’t match this preview. Run preview again from the pair.",
  merge_preview_schema_mismatch: "Preview format is outdated. Run preview again after refresh.",
  merge_survivor_not_eligible: "The survivor record is no longer eligible to absorb a merge.",
  merge_regulatory_blocking_conflict:
    "MC, USDOT, or CVOR conflict: both sides have different values. Align regulatory IDs (or clear one side) before merge.",
  merge_source_already_merged_elsewhere:
    "The source record was already merged into a different broker. Confirm survivor and source, or run a fresh preview.",
  merge_preview_payload_invalid: "Stored preview is unreadable. Contact support if this persists.",
  global_booking_broker_not_found: "One of the brokers no longer exists.",
  duplicate_candidate_not_found: "Duplicate candidate not found.",
  duplicate_candidate_pair_mismatch: "Candidate doesn’t match this broker pair.",
};

const FIELD_LABEL: Record<string, string> = {
  name: "primary name",
  legal_name: "legal name",
  display_name: "display name",
};

export function mergeResolutionFieldLabel(field: string): string {
  return FIELD_LABEL[field] ?? field.replace(/_/g, " ");
}

/** User-facing title for execute response `status` (not an HTTP error). */
export function mergeExecuteStatusLabel(status: "completed" | "already_completed"): string {
  if (status === "already_completed") {
    return "This merge was already completed. No further changes were made.";
  }
  return "Merge completed.";
}

export function friendlyMergeErrorMessage(detail: string): string {
  const d = detail.trim();
  if (d.startsWith("merge_resolution_required:")) {
    const field = d.slice("merge_resolution_required:".length).trim();
    const label = mergeResolutionFieldLabel(field);
    return `Choose which ${label} to keep on the surviving record before merging.`;
  }
  return DIRECT[d] ?? d;
}

/** Extract `detail` string from a thrown `PlatformAdminHttpError` body when possible. */
export function parseDetailFromErrorBody(bodyText: string, fallbackMessage: string): string {
  try {
    const j = JSON.parse(bodyText) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
  } catch {
    /* ignore */
  }
  return fallbackMessage;
}
