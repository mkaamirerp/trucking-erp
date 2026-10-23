import type { WorkspaceDraftFields } from "@/loadWorkspace/loadWorkspaceShared";
import { hasUsefulStopIdentity } from "@/loadWorkspace/loadParseStops";
import { validateDraftStopsClassifiedForSave } from "@/loadWorkspace/loadStopClassification";

/** True when persisted draft_json has no meaningful commercial content (default empty template). */
export function isWorkspaceCommercialSnapshotEmpty(fields: WorkspaceDraftFields): boolean {
  if (fields.brokerLoadReference.trim()) return false;
  if (fields.commodity.trim()) return false;
  if (fields.rate.trim()) return false;
  if (fields.customerRate.trim()) return false;
  if (fields.brokerNameSnapshot.trim()) return false;
  if (fields.miles.trim()) return false;
  for (const stop of fields.draftStops) {
    if (hasUsefulStopIdentity(stop)) return false;
  }
  return true;
}

/** Blocks Create load / promote — save draft may still store work-in-progress. */
export function validateWorkspaceReadyToPromote(fields: WorkspaceDraftFields): string | null {
  const stopErr = validateDraftStopsClassifiedForSave(fields.draftStops);
  if (stopErr) return stopErr;
  if (isWorkspaceCommercialSnapshotEmpty(fields)) {
    return "Parse a rate confirmation or enter broker, reference, rate, commodity, or stops before creating a load.";
  }
  return null;
}
