import type { LoadDocumentParseResponse, LoadWorkspaceDraft } from "@/api";
import { createEmptyParseHydrationState } from "@/loadWorkspace/loadParseHydrationState";
import { computeLoadWorkspacePdfHydrationResult } from "@/loadWorkspace/loadParseHydration";

export function loadDocumentParseFromAcceptedJson(
  accepted: Record<string, unknown> | null | undefined,
): LoadDocumentParseResponse | null {
  if (!accepted || typeof accepted !== "object") return null;
  const doc = accepted.document;
  const extracted = accepted.extracted;
  if (!doc || typeof doc !== "object" || !extracted || typeof extracted !== "object") return null;
  return accepted as LoadDocumentParseResponse;
}

export function workspaceReferenceTextFromDraft(draft: LoadWorkspaceDraft): string {
  const accepted = loadDocumentParseFromAcceptedJson(draft.accepted_parse_json ?? null);
  return (accepted?.raw_text ?? "").trim();
}

export function workspacePdfHydrationUxFromDraft(draft: LoadWorkspaceDraft) {
  const accepted = loadDocumentParseFromAcceptedJson(draft.accepted_parse_json ?? null);
  if (!accepted) {
    return {
      warnings: [] as string[],
      appliedLabels: null as string[] | null,
      fieldConfidence: {} as Record<string, string>,
      parseConfidenceTier: "neutral" as const,
    };
  }
  const ux = computeLoadWorkspacePdfHydrationResult(accepted, {
    resolvedBrokerId: null,
    resolvedBrokerContactId: null,
    brokerContactMatched: false,
    mcOrDotAttempted: false,
    unresolvedStopCount: 0,
    parseHydrationState: createEmptyParseHydrationState(),
  });
  return {
    warnings: ux.warnings,
    appliedLabels: ux.appliedLabels,
    fieldConfidence: ux.fieldConfidence,
    parseConfidenceTier: ux.parseConfidenceTier,
  };
}

export function draftHasReadyRateConfirmationPdf(draft: LoadWorkspaceDraft | null | undefined): boolean {
  return draft?.pdf_upload_state === "ready" && Boolean(draft.pdf_sha256);
}
