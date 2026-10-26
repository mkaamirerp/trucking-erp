/**
 * Session-only parse hydration ownership (Issue I18).
 * Distinguishes parser-applied values from operator manual edits without DB persistence.
 */
import type { LoadDocumentParseResponse } from "@/api";
import type { ApplyLoadDocumentParseCallbacks } from "@/loadWorkspace/applyLoadDocumentParseResponse";
import type { LoadPersistParams, WorkspaceDraftFields } from "@/loadWorkspace/loadWorkspaceShared";
import { filterMeaningfulParsedStops, hasUsefulStopIdentity } from "@/loadWorkspace/loadParseStops";
import {
  draftLoadReferencesDifferFromParsedExtract,
  workspaceReferencesFromParse,
} from "@/loadWorkspace/loadOperationalReferences";

export type ParseContactFieldKey =
  | "brokerContactName"
  | "brokerContactPhone"
  | "brokerContactEmail";

export const PARSE_CONTACT_FIELD_CONFIDENCE_KEYS: Record<ParseContactFieldKey, string> = {
  brokerContactName: "broker_contact_name_snapshot",
  brokerContactPhone: "broker_contact_phone_snapshot",
  brokerContactEmail: "broker_contact_email_snapshot",
};

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
  lastAppliedContactValues: Map<ParseContactFieldKey, string>;
  manualContactFieldKeys: Set<ParseContactFieldKey>;
  /** Operator edited route stops — re-parse must not replace them silently. */
  stopsRouteManuallyEdited: boolean;
  /** Dispatcher picked or corrected broker id/name — re-parse must not re-resolve MC/DOT. */
  brokerIdentityLocked: boolean;
  /** Dispatcher chose a broker contact row — re-parse must not auto-match a different contact. */
  brokerContactIdManuallySelected: boolean;
  /** Operator-reviewed load-level references differ from last parser extract. */
  loadReferencesManuallyEdited: boolean;
}

export function createEmptyParseHydrationState(): ParseHydrationState {
  return {
    lastAppliedKeys: new Set(),
    manualOverrideKeys: new Set(),
    lastAppliedValues: new Map(),
    lastAppliedContactValues: new Map(),
    manualContactFieldKeys: new Set(),
    stopsRouteManuallyEdited: false,
    brokerIdentityLocked: false,
    brokerContactIdManuallySelected: false,
    loadReferencesManuallyEdited: false,
  };
}

function cloneParseHydrationState(state: ParseHydrationState): ParseHydrationState {
  return {
    lastAppliedKeys: new Set(state.lastAppliedKeys),
    manualOverrideKeys: new Set(state.manualOverrideKeys),
    lastAppliedValues: new Map(state.lastAppliedValues),
    lastAppliedContactValues: new Map(state.lastAppliedContactValues),
    manualContactFieldKeys: new Set(state.manualContactFieldKeys),
    stopsRouteManuallyEdited: state.stopsRouteManuallyEdited,
    brokerIdentityLocked: state.brokerIdentityLocked,
    brokerContactIdManuallySelected: state.brokerContactIdManuallySelected,
    loadReferencesManuallyEdited: state.loadReferencesManuallyEdited,
  };
}

export function markStopsRouteManuallyEdited(state: ParseHydrationState): void {
  state.stopsRouteManuallyEdited = true;
}

export function markBrokerIdentityLocked(state: ParseHydrationState): void {
  state.brokerIdentityLocked = true;
}

export function markBrokerContactIdManuallySelected(state: ParseHydrationState): void {
  state.brokerContactIdManuallySelected = true;
}

export function markLoadReferencesManuallyEdited(state: ParseHydrationState): void {
  state.loadReferencesManuallyEdited = true;
}

function normBrokerLabel(v: string | null | undefined): string {
  return (v ?? "").trim().toLowerCase();
}

/** Reopen draft: broker id/name no longer matches accepted parse broker snapshot. */
export function inferBrokerIdentityLocked(
  fields: WorkspaceDraftFields,
  ex: LoadDocumentParseResponse["extracted"],
): boolean {
  if (inferParseManualOverridesFromDraft(fields, ex).has("brokerNameSnapshot")) return true;
  const parsedName = trimmedNonEmpty(ex.broker_name_snapshot);
  if (fields.brokerId != null && parsedName != null) {
    if (normBrokerLabel(fields.brokerNameSnapshot) !== normBrokerLabel(parsedName)) return true;
  }
  return false;
}

export function inferBrokerContactIdManuallySelected(
  fields: WorkspaceDraftFields,
  ex: LoadDocumentParseResponse["extracted"],
): boolean {
  if (fields.brokerContactId == null) return false;
  if (inferParseContactManualFieldKeys(fields, ex).size > 0) return true;
  if (inferBrokerIdentityLocked(fields, ex)) return true;
  return false;
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

export function registerManualContactFieldEdit(
  state: ParseHydrationState,
  key: ParseContactFieldKey,
  newValue: string,
): void {
  if (!state.lastAppliedContactValues.has(key)) return;
  const last = state.lastAppliedContactValues.get(key) ?? "";
  if (newValue.trim() !== last.trim()) {
    state.manualContactFieldKeys.add(key);
  }
}

function contactStringFromExtracted(
  key: ParseContactFieldKey,
  ex: LoadDocumentParseResponse["extracted"],
): string | null {
  switch (key) {
    case "brokerContactName":
      return trimmedNonEmpty(ex.broker_contact_name_snapshot);
    case "brokerContactPhone":
      return trimmedNonEmpty(ex.broker_contact_phone_snapshot);
    case "brokerContactEmail":
      return trimmedNonEmpty(ex.broker_contact_email_snapshot);
    default:
      return null;
  }
}

function contactDraftValue(fields: WorkspaceDraftFields, key: ParseContactFieldKey): string {
  switch (key) {
    case "brokerContactName":
      return fields.brokerContactNameSnapshot ?? "";
    case "brokerContactPhone":
      return fields.brokerContactPhoneSnapshot ?? "";
    case "brokerContactEmail":
      return fields.brokerContactEmailSnapshot ?? "";
    default:
      return "";
  }
}

const PARSE_CONTACT_FIELD_KEYS: ParseContactFieldKey[] = [
  "brokerContactName",
  "brokerContactPhone",
  "brokerContactEmail",
];

/** field_confidence keys for UI when contact differs from accepted parse extract. */
export function inferParseContactConfidenceManualKeys(
  fields: WorkspaceDraftFields,
  ex: LoadDocumentParseResponse["extracted"],
): Set<string> {
  const out = new Set<string>();
  const norm = (v: string) => v.trim();
  for (const key of PARSE_CONTACT_FIELD_KEYS) {
    const parsed = contactStringFromExtracted(key, ex);
    if (parsed == null) continue;
    if (norm(contactDraftValue(fields, key)) !== norm(parsed)) {
      out.add(PARSE_CONTACT_FIELD_CONFIDENCE_KEYS[key]);
    }
  }
  return out;
}

export function inferParseContactManualFieldKeys(
  fields: WorkspaceDraftFields,
  ex: LoadDocumentParseResponse["extracted"],
): Set<ParseContactFieldKey> {
  const out = new Set<ParseContactFieldKey>();
  const norm = (v: string) => v.trim();
  for (const key of PARSE_CONTACT_FIELD_KEYS) {
    const parsed = contactStringFromExtracted(key, ex);
    if (parsed == null) continue;
    if (norm(contactDraftValue(fields, key)) !== norm(parsed)) {
      out.add(key);
    }
  }
  return out;
}

export function applyScalarDraftValueToLoadPersist(
  params: LoadPersistParams,
  key: ParseScalarFieldKey,
  fields: WorkspaceDraftFields,
): void {
  switch (key) {
    case "brokerNameSnapshot":
      params.brokerNameSnapshot = fields.brokerNameSnapshot;
      break;
    case "brokerLoadReference":
      params.brokerLoadReference = fields.brokerLoadReference;
      break;
    case "freightMode":
      params.mode = fields.freightMode;
      break;
    case "equipmentType":
      params.equipmentType = fields.equipmentType;
      break;
    case "trailerType":
      params.trailerType = fields.trailerType;
      break;
    case "trailerSize":
      params.trailerSize = fields.trailerSize;
      break;
    case "commodity":
      params.commodity = fields.commodity;
      break;
    case "estimatedWeight":
      params.estimatedWeight = fields.estimatedWeight;
      break;
    case "temperatureRequirement":
      params.temperatureRequirement = fields.temperatureRequirement;
      break;
    case "rate":
      params.rate = fields.rate;
      break;
    case "customerRate":
      params.customerRate = fields.customerRate;
      break;
    case "miles":
      params.miles = fields.miles;
      break;
    default:
      break;
  }
}

export function applyContactDraftValueToLoadPersist(
  params: LoadPersistParams,
  key: ParseContactFieldKey,
  fields: WorkspaceDraftFields,
): void {
  switch (key) {
    case "brokerContactName":
      params.brokerContactNameSnapshot = fields.brokerContactNameSnapshot;
      break;
    case "brokerContactPhone":
      params.brokerContactPhoneSnapshot = fields.brokerContactPhoneSnapshot;
      break;
    case "brokerContactEmail":
      params.brokerContactEmailSnapshot = fields.brokerContactEmailSnapshot;
      break;
    default:
      break;
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
  for (const key of PARSE_CONTACT_FIELD_KEYS) {
    const applied = contactStringFromExtracted(key, ex);
    if (applied != null) {
      state.lastAppliedContactValues.set(key, applied);
    }
  }
  for (const key of inferParseContactManualFieldKeys(fields, ex)) {
    state.manualContactFieldKeys.add(key);
  }
  state.stopsRouteManuallyEdited = draftStopsDifferFromParsedExtract(fields, ex);
  state.brokerIdentityLocked = inferBrokerIdentityLocked(fields, ex);
  state.brokerContactIdManuallySelected = inferBrokerContactIdManuallySelected(fields, ex);
  state.loadReferencesManuallyEdited = draftLoadReferencesDifferFromParsedExtract(
    fields.loadReferences,
    ex.references,
  );
  return state;
}

/** True when saved draft stops are not a straight reflection of parsed stop rows. */
export function draftStopsDifferFromParsedExtract(
  fields: WorkspaceDraftFields,
  ex: LoadDocumentParseResponse["extracted"],
): boolean {
  const parsed = filterMeaningfulParsedStops(ex.stops ?? []);
  if (parsed.length === 0) return false;
  const draft = [...fields.draftStops]
    .filter((s) => hasUsefulStopIdentity(s))
    .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
  if (draft.length !== parsed.length) return true;
  const fingerprint = (s: {
    stop_type?: string | null;
    city?: string | null;
    state_or_province?: string | null;
    facility_name?: string | null;
    appointment_date?: string | null;
    appointment_time_text?: string | null;
    reference_number?: string | null;
    notes?: string | null;
  }) =>
    [
      (s.stop_type ?? "").toUpperCase(),
      (s.city ?? "").trim(),
      (s.state_or_province ?? "").trim(),
      (s.facility_name ?? "").trim(),
      (s.appointment_date ?? "").trim(),
      (s.appointment_time_text ?? "").trim(),
      (s.reference_number ?? "").trim(),
      (s.notes ?? "").trim(),
    ].join("|");
  for (let i = 0; i < parsed.length; i++) {
    const p = parsed[i];
    const d = draft[i];
    const pt = (p.stop_type ?? "").toLowerCase();
    const mapped =
      pt === "pickup" ? "PICKUP" : pt === "delivery" ? "DELIVERY" : pt === "drop" ? "DROP" : "UNRESOLVED";
    if (
      fingerprint({
        stop_type: mapped,
        city: p.city,
        state_or_province: p.state_or_province,
        facility_name: p.facility_name,
        appointment_date: p.appointment_date,
        appointment_time_text: p.appointment_time_text,
        reference_number: p.reference_number,
        notes: p.notes,
      }) !== fingerprint(d)
    ) {
      return true;
    }
  }
  return false;
}
