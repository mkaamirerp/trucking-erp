/**
 * Session-only parse hydration ownership (Issue I18).
 * Distinguishes parser-applied values from operator manual edits without DB persistence.
 */
import type { LoadDocumentParseResponse } from "@/api";
import type { ApplyLoadDocumentParseCallbacks } from "@/loadWorkspace/applyLoadDocumentParseResponse";

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
