/**
 * Human-readable labels for EmailThread.routing_reason (machine-oriented string from API).
 *
 * Bridge: primary code + optional ``|`` segments (e.g. review_detail, qr_extractions). A later review-workflow
 * pass should use stable primary codes on the thread and separate structured fields / history instead of growing
 * this string format.
 */

export function routingReasonBaseAndPrimary(raw: string): { base: string; primary: string } {
  const base = raw.replace(/\|qr_extractions=\d+$/i, "").trim();
  const primary = base.split("|")[0]?.trim() || base;
  return { base, primary };
}

export function formatRoutingReason(raw: string | null | undefined): string {
  if (!raw) return "Not yet classified.";
  const { base, primary } = routingReasonBaseAndPrimary(raw);
  if (primary === "email_intake_pdf_parse_review") {
    const pipe = base.match(/\|gate_detail=([^|]+)/i);
    if (pipe) {
      return "PDF parsed — review snapshot ready: " + pipe[1].replace(/_/g, " ");
    }
    return "PDF parsed — open intake review to prefill or create a load.";
  }
  if (primary === "tql_pdf_not_high_confidence") {
    const pipe = base.match(/\|gate_detail=([^|]+)/i);
    if (pipe) {
      return "PDF did not yield a guarded parse snapshot: " + pipe[1].replace(/_/g, " ");
    }
  }
  const tqlColon = /^tql_pdf_not_high_confidence:/i;
  if (tqlColon.test(base)) {
    return "PDF did not yield a guarded parse snapshot: " + base.replace(tqlColon, "").replace(/_/g, " ");
  }
  if (primary === "broker_intake_blocked") return "Broker blocked from intake (policy). Review required.";
  if (primary === "broker_resolve_ambiguous") {
    return "Multiple brokers matched the same rule — review required.";
  }
  if (primary === "global_broker_resolve_ambiguous") {
    return "Multiple global reference brokers matched — review required.";
  }
  if (primary === "global_broker_match_requires_workspace") {
    return "Global broker matched; workspace auto-create is off. Link or create a broker, then retry.";
  }
  if (primary === "global_broker_tier_d_requires_review") {
    return "MC/DOT matched a global broker; confirm and link in workspace before auto intake.";
  }
  if (primary === "global_broker_header_vs_mc_dot_disagreement") {
    return "The email’s From/domain/sender identity and the MC/DOT global reference disagree — review required.";
  }
  if (primary === "intake_broker_conflicting_signals") {
    return (
      "A broker is already matched from this email (sender / domain / alias), but MC or USDOT found in the message or PDF points to a different global broker than the one this workspace broker is linked to. " +
      "Confirm the broker (or update its global link) before treating intake as clean — review stays on until you resolve it."
    );
  }
  if (/^duplicate_pdf_sha256\|prior_load_id=\d+/i.test(base)) {
    return "This PDF likely matches an already-ingested load (duplicate content). Review required.";
  }
  return base.replace(/_/g, " ");
}
