/**
 * Slice 16A: single entry for Load workspace PDF parse → draft hydration + UX metadata.
 * Draft field mapping lives in applyLoadDocumentParseResponse (source of truth for setters).
 */
import type { LoadDocumentParseResponse } from "@/api";
import {
  applyLoadDocumentParseResponse,
  type ApplyLoadDocumentParseCallbacks,
  type ApplyLoadDocumentParseSummary,
} from "@/loadWorkspace/applyLoadDocumentParseResponse";
import { buildWorkspacePdfParseAppliedLabels } from "@/loadWorkspace/loadParseAppliedLabels";
import { describeWorkspacePdfParseOutcome } from "@/loadWorkspace/loadParseOutcome";

/** Toolbar tone after parse hydration (matches LoadWorkspacePage WorkspaceToolbarTone). */
export type LoadWorkspacePdfHydrationTone = "success" | "warning" | "error" | "neutral";

export interface LoadWorkspacePdfHydrationResult {
  /** Broker resolution summary from applyLoadDocumentParseResponse. */
  summary: ApplyLoadDocumentParseSummary;
  warnings: string[];
  toolbar: { text: string; tone: LoadWorkspacePdfHydrationTone };
  appliedLabels: string[] | null;
}

/**
 * Computes warnings, toolbar message, and applied-field labels after extracted data
 * has been (or would be) merged into draft state. Pure — used by tests and by the full hydrator.
 */
export function computeLoadWorkspacePdfHydrationResult(
  res: LoadDocumentParseResponse,
  summary: ApplyLoadDocumentParseSummary,
): LoadWorkspacePdfHydrationResult {
  const warnings = res.warnings ?? [];
  const outcome = describeWorkspacePdfParseOutcome(res.extracted, res.raw_text, warnings);
  const tone: LoadWorkspacePdfHydrationTone =
    outcome.tone === "success" ? "success" : outcome.tone === "warning" ? "warning" : "neutral";
  const appliedLabels = buildWorkspacePdfParseAppliedLabels(res.extracted, res.raw_text, {
    mcOrDotAttempted: summary.mcOrDotAttempted,
    resolvedBrokerId: summary.resolvedBrokerId,
    brokerContactMatched: summary.brokerContactMatched,
  });
  return {
    summary,
    warnings,
    toolbar: { text: outcome.headline, tone },
    appliedLabels: appliedLabels.length > 0 ? appliedLabels : null,
  };
}

/**
 * Apply parse-document response to workspace draft via callbacks, then return structured UX payload.
 * Behavior matches pre–Slice 16A LoadWorkspacePage.onParseWorkspacePdf (apply + warnings + toolbar + labels).
 */
export async function hydrateLoadWorkspaceFromParseResponse(
  res: LoadDocumentParseResponse,
  cbs: ApplyLoadDocumentParseCallbacks,
): Promise<LoadWorkspacePdfHydrationResult> {
  const summary = await applyLoadDocumentParseResponse(res, cbs);
  return computeLoadWorkspacePdfHydrationResult(res, summary);
}
