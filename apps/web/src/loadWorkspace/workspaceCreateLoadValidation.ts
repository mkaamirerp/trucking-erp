import type { Broker, LoadWorkspaceDraft } from "@/api";
import type { WorkspaceDraftFields } from "@/loadWorkspace/loadWorkspaceShared";
import type { DraftStop } from "@/loadWorkspace/loadWorkspaceShared";
import { validateDraftStopsClassifiedForSave } from "@/loadWorkspace/loadStopClassification";
import type { ParseHydrationState } from "@/loadWorkspace/loadParseHydrationState";

export type CreateLoadGateResult = {
  /** When set, block create and show alert — mandatory fields missing. */
  hardBlockMessage: string | null;
  /** Shown in confirm dialog when hard requirements pass. */
  missingOptionalLabels: string[];
};

export const BROKER_LOAD_NUMBER_PO_LABEL = "Broker load # / PO #";
export const INTERNAL_LOAD_NUMBER_LABEL = "Load number";

export function brokerDisplayName(b: Broker): string {
  return (b.display_name || b.name || b.legal_name || "").trim();
}

export function resolveBrokerCarrierName(
  fields: WorkspaceDraftFields,
  brokers: Broker[],
): string {
  const snap = fields.brokerNameSnapshot.trim();
  if (snap) return snap;
  if (fields.brokerId != null) {
    const b = brokers.find((x) => x.id === fields.brokerId);
    if (b) return brokerDisplayName(b);
  }
  return "";
}

function sortedStops(stops: DraftStop[]): DraftStop[] {
  return [...stops].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
}

export function firstStopOfTypes(stops: DraftStop[], types: string[]): DraftStop | null {
  const want = new Set(types.map((t) => t.toUpperCase()));
  for (const s of sortedStops(stops)) {
    if (want.has((s.stop_type || "").toUpperCase())) return s;
  }
  return null;
}

/** Broker's number from the rate con (not our internal TruckERP load number). */
export function hasBrokerLoadNumberOrPo(fields: WorkspaceDraftFields): boolean {
  return fields.brokerLoadReference.trim().length > 0;
}

export function draftHasParsedPdf(
  draft: LoadWorkspaceDraft | null,
  parseHydration: ParseHydrationState,
): boolean {
  if (draft?.accepted_parse_json != null && draft.accepted_parse_json !== undefined) return true;
  if ((draft?.pdf_filename || "").trim()) return true;
  return parseHydration.lastAppliedKeys.size > 0;
}

/** Manual create (no parsed PDF): pickup + delivery city/state and stop classification only. */
export function listManualCreateHardMissing(fields: WorkspaceDraftFields): string[] {
  const hardMissing: string[] = [];

  const stopClassErr = validateDraftStopsClassifiedForSave(fields.draftStops);
  if (stopClassErr) {
    hardMissing.push(stopClassErr);
  }

  const pickup = firstStopOfTypes(fields.draftStops, ["PICKUP"]);
  const delivery = firstStopOfTypes(fields.draftStops, ["DELIVERY", "DROP"]);

  if (!pickup) {
    hardMissing.push("At least one pickup stop");
  } else {
    if (!(pickup.city ?? "").trim()) hardMissing.push("Pickup city");
    if (!(pickup.state_or_province ?? "").trim()) hardMissing.push("Pickup state or province");
  }

  if (!delivery) {
    hardMissing.push("At least one delivery stop");
  } else {
    if (!(delivery.city ?? "").trim()) hardMissing.push("Delivery city");
    if (!(delivery.state_or_province ?? "").trim()) hardMissing.push("Delivery state or province");
  }

  return hardMissing;
}

/** Soft informational list (parsed create + drafts panel); never blocks create after parse. */
export function listCreateLoadSoftNotProvided(
  fields: WorkspaceDraftFields,
  brokers: Broker[],
): string[] {
  const items: string[] = [];

  if (!resolveBrokerCarrierName(fields, brokers)) {
    items.push("Broker");
  }
  if (!hasBrokerLoadNumberOrPo(fields)) {
    items.push(BROKER_LOAD_NUMBER_PO_LABEL);
  }

  const pickup = firstStopOfTypes(fields.draftStops, ["PICKUP"]);
  const delivery = firstStopOfTypes(fields.draftStops, ["DELIVERY", "DROP"]);

  if (!pickup) {
    items.push("Pickup stop");
  } else {
    if (!(pickup.city ?? "").trim()) items.push("Pickup city");
    if (!(pickup.state_or_province ?? "").trim()) items.push("Pickup state or province");
  }

  if (!delivery) {
    items.push("Delivery stop");
  } else {
    if (!(delivery.city ?? "").trim()) items.push("Delivery city");
    if (!(delivery.state_or_province ?? "").trim()) items.push("Delivery state or province");
  }

  if (!fields.commodity.trim()) items.push("Commodity");
  if (!fields.rate.trim()) items.push("Rate");

  return items;
}

export function formatSoftNotProvidedLine(items: string[]): string | null {
  if (items.length === 0) return null;
  return `Not provided: ${items.join(", ")}`;
}

export function formatManualHardMissingLine(items: string[]): string | null {
  if (items.length === 0) return null;
  return `Missing: ${items.join(", ")}`;
}

export function evaluateCreateLoadGate(
  fields: WorkspaceDraftFields,
  brokers: Broker[],
): CreateLoadGateResult {
  const hardMissing = listManualCreateHardMissing(fields);

  if (hardMissing.length > 0) {
    return {
      hardBlockMessage: `Cannot create load yet. Required:\n\n• ${hardMissing.join("\n• ")}`,
      missingOptionalLabels: [],
    };
  }

  const pickup = firstStopOfTypes(fields.draftStops, ["PICKUP"]);
  const delivery = firstStopOfTypes(fields.draftStops, ["DELIVERY", "DROP"]);

  const missingOptional: string[] = [];
  if (!resolveBrokerCarrierName(fields, brokers)) missingOptional.push("Broker");
  if (!hasBrokerLoadNumberOrPo(fields)) missingOptional.push(BROKER_LOAD_NUMBER_PO_LABEL);
  if (!fields.commodity.trim()) missingOptional.push("Commodity");
  if (!fields.rate.trim()) missingOptional.push("Rate");
  if (!fields.miles.trim()) missingOptional.push("Miles");
  if (!(pickup?.facility_name ?? "").trim()) missingOptional.push("Pickup facility name");
  if (!(delivery?.facility_name ?? "").trim()) missingOptional.push("Delivery facility name");
  if (!(pickup?.street ?? "").trim()) missingOptional.push("Pickup street address");
  if (!(delivery?.street ?? "").trim()) missingOptional.push("Delivery street address");
  if (!fields.equipmentType.trim()) missingOptional.push("Equipment type");

  return { hardBlockMessage: null, missingOptionalLabels: missingOptional };
}

export function formatCommercialGateConfirm(
  missing: string[],
  mode: "create" | "save",
): string {
  const anyway = mode === "save" ? "Save for later anyway?" : "Create load anyway?";
  if (missing.length === 0) {
    return mode === "save"
      ? "Save this draft for later with the information entered?"
      : "Create this load with the information entered?";
  }
  return "Some fields are still empty:\n\n• " + missing.join("\n• ") + `\n\n${anyway}`;
}

/** @deprecated Use formatCommercialGateConfirm(missing, "create") */
export function formatCreateLoadAnywayConfirm(missing: string[]): string {
  return formatCommercialGateConfirm(missing, "create");
}

export type WorkspaceCommercialGateOutcome = "proceed" | "blocked" | "cancelled";

/** Primary action label for the commercial gate modal (replaces native confirm OK). */
export function commercialGatePrimaryActionLabel(mode: "create" | "save"): string {
  return mode === "save" ? "Save for later anyway" : "Create load anyway";
}

export type WorkspaceCommercialGatePrompt =
  | { outcome: "blocked"; alertMessage: string }
  | { outcome: "confirm"; message: string; mode: "create" | "save" };

/** Evaluate gate; caller shows modal when outcome is confirm (custom buttons, not window.confirm). */
export function resolveWorkspaceCommercialGatePrompt(
  fields: WorkspaceDraftFields,
  brokers: Broker[],
  mode: "create" | "save",
): WorkspaceCommercialGatePrompt {
  const gate = evaluateCreateLoadGate(fields, brokers);
  if (gate.hardBlockMessage) {
    return { outcome: "blocked", alertMessage: gate.hardBlockMessage };
  }
  return {
    outcome: "confirm",
    message: formatCommercialGateConfirm(gate.missingOptionalLabels, mode),
    mode,
  };
}
