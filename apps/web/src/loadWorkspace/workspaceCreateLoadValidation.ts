import type { Broker } from "@/api";
import type { WorkspaceDraftFields } from "@/loadWorkspace/loadWorkspaceShared";
import type { DraftStop } from "@/loadWorkspace/loadWorkspaceShared";
import { validateDraftStopsClassifiedForSave } from "@/loadWorkspace/loadStopClassification";

export type CreateLoadGateResult = {
  /** When set, block create and show alert — mandatory fields missing. */
  hardBlockMessage: string | null;
  /** Shown in confirm dialog when hard requirements pass. */
  missingOptionalLabels: string[];
};

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

/** Task 2b: broker load number, internal load #, or any parsed reference row (e.g. PO #). */
export function hasLoadNumberOrPo(fields: WorkspaceDraftFields): boolean {
  if (fields.brokerLoadReference.trim()) return true;
  if (fields.loadNumber.trim()) return true;
  return fields.loadReferences.some((r) => (r.value || "").trim().length > 0);
}

function locationLabel(stop: DraftStop | null, role: string): string {
  if (!stop) return `${role} stop`;
  const city = (stop.city ?? "").trim();
  const region = (stop.state_or_province ?? "").trim();
  if (!city && !region) return `${role} (city and state/province)`;
  if (!city) return `${role} (city)`;
  if (!region) return `${role} (state/province)`;
  return `${role}: ${city}, ${region}`;
}

export function listCreateLoadHardMissing(
  fields: WorkspaceDraftFields,
  brokers: Broker[],
): string[] {
  const hardMissing: string[] = [];

  const stopClassErr = validateDraftStopsClassifiedForSave(fields.draftStops);
  if (stopClassErr) {
    hardMissing.push(stopClassErr);
  }

  const carrier = resolveBrokerCarrierName(fields, brokers);
  if (!carrier) {
    hardMissing.push("Broker/Carrier (type a name or pick from suggestions)");
  }

  if (!hasLoadNumberOrPo(fields)) {
    hardMissing.push("Load # / PO #");
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

export function evaluateCreateLoadGate(
  fields: WorkspaceDraftFields,
  brokers: Broker[],
): CreateLoadGateResult {
  const hardMissing = listCreateLoadHardMissing(fields, brokers);

  if (hardMissing.length > 0) {
    return {
      hardBlockMessage: `Cannot create load yet. Required:\n\n• ${hardMissing.join("\n• ")}`,
      missingOptionalLabels: [],
    };
  }

  const pickup = firstStopOfTypes(fields.draftStops, ["PICKUP"]);
  const delivery = firstStopOfTypes(fields.draftStops, ["DELIVERY", "DROP"]);

  const missingOptional: string[] = [];
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
