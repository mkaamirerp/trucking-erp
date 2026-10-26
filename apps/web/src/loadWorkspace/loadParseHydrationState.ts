/**
 * Session-only parse hydration ownership (Issue I18).
 * Distinguishes parser-applied values from operator manual edits without DB persistence.
 */
import type { LoadDocumentParseResponse } from "@/api";
import type { ApplyLoadDocumentParseCallbacks } from "@/loadWorkspace/applyLoadDocumentParseResponse";
import type { WorkspaceDraftFields } from "@/loadWorkspace/loadWorkspaceShared";

export type ParseScalarFieldKey =
  | "brokerNameSnapshot"
  | "brokerLoadReference"
  | "freightMode"
  | "equipmentType"
  | "trailerType"
  | "trailerSize"
  | "commodity"
  | "estimatedWeight"
  | "temperatureRequirement"
  | "rate"
  | "customerRate"
  | "miles";

export interface ParseHydrationState {
  lastAppliedKeys: Set<ParseScalarFieldKey>;
  manualOverrideKeys: Set<ParseScalarFieldKey>;
  lastAppliedValues: Map<ParseScalarFieldKey, string>;
}

export function createEmptyParseHydrationState(): ParseHydrationState {
  return {
    lastAppliedKeys: new Set(),
    manualOverrideKeys: new Set(),
    lastAppliedValues: new Map(),
  };
}

function cloneParseHydrationState(state: ParseHydrationState): ParseHydrationState {
  return {
    lastAppliedKeys: new Set(state.lastAppliedKeys),
    manualOverrideKeys: new Set(state.manualOverrideKeys),
    lastAppliedValues: new Map(state.lastAppliedValues),
  };
}

function trimmedNonEmpty(v: string | null | undefined): string | null {
  const t = (v ?? "").trim();
  return t ? t : null;
}

export function extractPresentParseScalarKeys(
  ex: LoadDocumentParseResponse["extracted"],
): Set<ParseScalarFieldKey> {
  const keys = new Set<ParseScalarFieldKey>();
  if (trimmedNonEmpty(ex.broker_name_snapshot)) keys.add("brokerNameSnapshot");
  if (trimmedNonEmpty(ex.broker_load_reference)) keys.add("brokerLoadReference");
  if (trimmedNonEmpty(ex.mode)) keys.add("freightMode");
  if (trimmedNonEmpty(ex.equipment_type)) keys.add("equipmentType");
  if (trimmedNonEmpty(ex.trailer_type)) keys.add("trailerType");
  if (trimmedNonEmpty(ex.trailer_size)) keys.add("trailerSize");
  if (trimmedNonEmpty(ex.commodity)) keys.add("commodity");
  if (ex.estimated_weight != null) keys.add("estimatedWeight");
  if (trimmedNonEmpty(ex.temperature_requirement)) keys.add("temperatureRequirement");
  if (ex.rate != null) keys.add("rate");
  if (ex.customer_rate != null) keys.add("customerRate");
  if (ex.miles != null) keys.add("miles");
  return keys;
}

function clearParseScalarField(key: ParseScalarFieldKey, cbs: ApplyLoadDocumentParseCallbacks): void {
  switch (key) {
    case "brokerNameSnapshot":
      cbs.setBrokerNameSnapshot("");
      break;
    case "brokerLoadReference":
      cbs.setBrokerLoadReference("");
      break;
    case "freightMode":
      cbs.setFreightMode("");
      break;
    case "equipmentType":
      cbs.setEquipmentType("");
      break;
    case "trailerType":
      cbs.setTrailerType("");
      break;
    case "trailerSize":
      cbs.setTrailerSize("");
      break;
    case "commodity":
      cbs.setCommodity("");
      break;
    case "estimatedWeight":
      cbs.setEstimatedWeight("");
      break;
    case "temperatureRequirement":
      cbs.setTemperatureRequirement("");
      break;
    case "rate":
      cbs.setRate("");
      break;
    case "customerRate":
      cbs.setCustomerRate("");
      break;
    case "miles":
      cbs.setMiles("");
      break;
    default:
      break;
  }
}

function applyParseScalarField(
  key: ParseScalarFieldKey,
  ex: LoadDocumentParseResponse["extracted"],
  cbs: ApplyLoadDocumentParseCallbacks,
): string | null {
  switch (key) {
    case "brokerNameSnapshot": {
      const v = trimmedNonEmpty(ex.broker_name_snapshot);
      if (v) cbs.setBrokerNameSnapshot(v);
      return v;
    }
    case "brokerLoadReference": {
      const v = trimmedNonEmpty(ex.broker_load_reference);
      if (v) cbs.setBrokerLoadReference(v);
      return v;
    }
    case "freightMode": {
      const v = trimmedNonEmpty(ex.mode);
      if (v) cbs.setFreightMode(v);
      return v;
    }
    case "equipmentType": {
      const v = trimmedNonEmpty(ex.equipment_type);
      if (v) cbs.setEquipmentType(v);
      return v;
    }
    case "trailerType": {
      const v = trimmedNonEmpty(ex.trailer_type);
      if (v) cbs.setTrailerType(v);
      return v;
    }
    case "trailerSize": {
      const v = trimmedNonEmpty(ex.trailer_size);
      if (v) cbs.setTrailerSize(v);
      return v;
    }
    case "commodity": {
      const v = trimmedNonEmpty(ex.commodity);
      if (v) cbs.setCommodity(v);
      return v;
    }
    case "estimatedWeight": {
      if (ex.estimated_weight != null) {
        const v = String(ex.estimated_weight);
        cbs.setEstimatedWeight(v);
        return v;
      }
      return null;
    }
    case "temperatureRequirement": {
      const v = trimmedNonEmpty(ex.temperature_requirement);
      if (v) cbs.setTemperatureRequirement(v);
      return v;
    }
    case "rate": {
      if (ex.rate != null) {
        const v = String(ex.rate);
        cbs.setRate(v);
        return v;
      }
      return null;
    }
    case "customerRate": {
      if (ex.customer_rate != null) {
        const v = String(ex.customer_rate);
        cbs.setCustomerRate(v);
        return v;
      }
      return null;
    }
    case "miles": {
      if (ex.miles != null) {
        const v = String(Math.round(ex.miles));
        cbs.setMiles(v);
        return v;
      }
      return null;
    }
    default:
      return null;
  }
}

/**
 * Clear parser-owned scalars omitted by the new document; apply present scalars unless manually overridden.
 */
export function applyParseScalarHydration(
  ex: LoadDocumentParseResponse["extracted"],
  cbs: ApplyLoadDocumentParseCallbacks,
  state: ParseHydrationState,
): ParseHydrationState {
  const next = cloneParseHydrationState(state);
  const present = extractPresentParseScalarKeys(ex);

  for (const key of next.lastAppliedKeys) {
    if (present.has(key) || next.manualOverrideKeys.has(key)) continue;
    clearParseScalarField(key, cbs);
    next.lastAppliedKeys.delete(key);
    next.lastAppliedValues.delete(key);
  }

  for (const key of present) {
    if (next.manualOverrideKeys.has(key)) continue;
    const applied = applyParseScalarField(key, ex, cbs);
    if (applied != null) {
      next.lastAppliedKeys.add(key);
      next.lastAppliedValues.set(key, applied);
    }
  }

  return next;
}

/** Call from workspace field onChange when the operator edits a parse-hydrated scalar. */
export function registerManualParseFieldEdit(
  state: ParseHydrationState,
  key: ParseScalarFieldKey,
  newValue: string,
): void {
  if (!state.lastAppliedKeys.has(key)) return;
  const last = state.lastAppliedValues.get(key) ?? "";
  if (newValue !== last) {
    state.manualOverrideKeys.add(key);
  }
}

function scalarStringFromExtracted(
  key: ParseScalarFieldKey,
  ex: LoadDocumentParseResponse["extracted"],
): string | null {
  switch (key) {
    case "brokerNameSnapshot":
      return trimmedNonEmpty(ex.broker_name_snapshot);
    case "brokerLoadReference":
      return trimmedNonEmpty(ex.broker_load_reference);
    case "freightMode":
      return trimmedNonEmpty(ex.mode);
    case "equipmentType":
      return trimmedNonEmpty(ex.equipment_type);
    case "trailerType":
      return trimmedNonEmpty(ex.trailer_type);
    case "trailerSize":
      return trimmedNonEmpty(ex.trailer_size);
    case "commodity":
      return trimmedNonEmpty(ex.commodity);
    case "estimatedWeight":
      return ex.estimated_weight != null ? String(ex.estimated_weight) : null;
    case "temperatureRequirement":
      return trimmedNonEmpty(ex.temperature_requirement);
    case "rate":
      return ex.rate != null ? String(ex.rate) : null;
    case "customerRate":
      return ex.customer_rate != null ? String(ex.customer_rate) : null;
    case "miles":
      return ex.miles != null ? String(Math.round(ex.miles)) : null;
    default:
      return null;
  }
}

/** After Save Draft / reopen: infer operator edits by diffing draft fields to accepted parse extract. */
export function inferParseManualOverridesFromDraft(
  fields: WorkspaceDraftFields,
  ex: LoadDocumentParseResponse["extracted"],
): Set<ParseScalarFieldKey> {
  const overrides = new Set<ParseScalarFieldKey>();
  const norm = (v: string) => v.trim();
  for (const key of extractPresentParseScalarKeys(ex)) {
    const parsed = scalarStringFromExtracted(key, ex);
    if (parsed == null) continue;
    const current = norm(scalarDraftValue(fields, key));
    if (current !== norm(parsed)) overrides.add(key);
  }
  return overrides;
}

function scalarDraftValue(fields: WorkspaceDraftFields, key: ParseScalarFieldKey): string {
  switch (key) {
    case "brokerNameSnapshot":
      return fields.brokerNameSnapshot ?? "";
    case "brokerLoadReference":
      return fields.brokerLoadReference ?? "";
    case "freightMode":
      return fields.freightMode ?? "";
    case "equipmentType":
      return fields.equipmentType ?? "";
    case "trailerType":
      return fields.trailerType ?? "";
    case "trailerSize":
      return fields.trailerSize ?? "";
    case "commodity":
      return fields.commodity ?? "";
    case "estimatedWeight":
      return fields.estimatedWeight ?? "";
    case "temperatureRequirement":
      return fields.temperatureRequirement ?? "";
    case "rate":
      return fields.rate ?? "";
    case "customerRate":
      return fields.customerRate ?? "";
    case "miles":
      return fields.miles ?? "";
    default:
      return "";
  }
}

/** Restore session hydration metadata when reopening a draft with accepted_parse_json. */
export function hydrationStateFromDraftAndParse(
  fields: WorkspaceDraftFields,
  ex: LoadDocumentParseResponse["extracted"],
): ParseHydrationState {
  const state = createEmptyParseHydrationState();
  for (const key of extractPresentParseScalarKeys(ex)) {
    const applied = scalarStringFromExtracted(key, ex);
    if (applied != null) {
      state.lastAppliedKeys.add(key);
      state.lastAppliedValues.set(key, applied);
    }
  }
  for (const key of inferParseManualOverridesFromDraft(fields, ex)) {
    state.manualOverrideKeys.add(key);
  }
  return state;
}
