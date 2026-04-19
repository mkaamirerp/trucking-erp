import type { LoadDocumentParseExtracted } from "../api";

export type WorkspacePdfParseResolutionSummary = {
  /** True iff `mcSnap || dotSnap` branch ran in `onParseWorkspacePdf`. */
  mcOrDotAttempted: boolean;
  /** Result of `resolveBrokerIdentity` when attempted. */
  resolvedBrokerId: number | null;
  /** True iff `matchBrokerContactFromParsed` returned a row and contact id was set. */
  brokerContactMatched: boolean;
};

function trimNonEmpty(v: string | null | undefined): boolean {
  return typeof v === "string" && v.trim().length > 0;
}

/**
 * Human-readable labels for what the load workspace PDF parse handler actually applied.
 * Mirrors `onParseWorkspacePdf` in `LoadWorkspacePage.tsx` — keep in sync when that handler changes.
 */
export function buildWorkspacePdfParseAppliedLabels(
  ex: LoadDocumentParseExtracted,
  rawText: string | null | undefined,
  resolution: WorkspacePdfParseResolutionSummary,
): string[] {
  const labels: string[] = [];

  if (trimNonEmpty(ex.broker_name_snapshot)) {
    labels.push("Broker name");
  }

  if (resolution.mcOrDotAttempted) {
    if (resolution.resolvedBrokerId != null) {
      labels.push("Broker matched (MC/DOT)");
    } else {
      labels.push("MC/DOT from document (no tenant match)");
    }
  }

  if (resolution.brokerContactMatched) {
    labels.push("Broker contact (matched to directory)");
  }
  if (trimNonEmpty(ex.broker_contact_name_snapshot)) {
    labels.push("Broker contact name");
  }
  if (trimNonEmpty(ex.broker_contact_phone_snapshot)) {
    labels.push("Broker contact phone");
  }
  if (trimNonEmpty(ex.broker_contact_email_snapshot)) {
    labels.push("Broker contact email");
  }

  if (trimNonEmpty(ex.broker_load_reference)) {
    labels.push("Broker load reference");
  }
  if (trimNonEmpty(ex.mode)) {
    labels.push("Mode");
  }
  if (trimNonEmpty(ex.equipment_type)) {
    labels.push("Equipment type");
  }
  if (trimNonEmpty(ex.trailer_type)) {
    labels.push("Trailer type");
  }
  if (trimNonEmpty(ex.trailer_size)) {
    labels.push("Trailer size");
  }
  if (trimNonEmpty(ex.commodity)) {
    labels.push("Commodity");
  }
  if (ex.estimated_weight != null) {
    labels.push("Estimated weight");
  }
  if (trimNonEmpty(ex.temperature_requirement)) {
    labels.push("Temperature requirement");
  }
  if (ex.rate != null) {
    labels.push("Rate");
  }
  if (ex.customer_rate != null) {
    labels.push("Customer rate");
  }
  if (ex.miles != null) {
    labels.push("Miles");
  }

  if (ex.stops?.length) {
    labels.push("Stops");
  }

  let notesBody = (rawText ?? "").trim() || "";
  const customsName = ex.customs_broker_name?.trim();
  if (customsName) {
    const cline = `Customs broker (from document): ${customsName}`;
    notesBody = notesBody ? `${notesBody}\n\n---\n${cline}` : cline;
  }
  if (notesBody.trim().length > 0) {
    labels.push("Notes / source text");
  }

  return labels;
}
