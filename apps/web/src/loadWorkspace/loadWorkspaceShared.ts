/**
 * Shared helpers and UI tokens for the canonical load workspace (create + edit).
 */
import type { Load, LoadDocumentParseReference, LoadStop, LoadStopWrite, LoadWritePayload } from "@/api";
import { sortedStops as sortStops } from "@/utils/loadStops";
import { hasUsefulStopIdentity } from "./loadParseStops";

/** Workspace shell mode — drives data source, save path, and chrome only; fields are identical. */
export type LoadWorkspaceMode = "manual" | "intake" | "detail" | "payroll" | "audit";

export type WorkspaceSection =
  | "HeaderIdentity"
  | "Parties"
  | "Stops"
  | "Equipment"
  | "Assignment"
  | "Documents"
  | "Notes"
  | "Settlement"
  | "AuditTimeline";

export const SECTION_CONFIG: Record<
  LoadWorkspaceMode,
  { visible: WorkspaceSection[]; editable: WorkspaceSection[]; defaultSection: WorkspaceSection }
> = {
  manual: {
    visible: ["HeaderIdentity", "Parties", "Stops", "Equipment", "Assignment", "Documents", "Notes"],
    editable: ["Parties", "Stops", "Equipment", "Assignment", "Documents", "Notes"],
    defaultSection: "Parties",
  },
  intake: {
    visible: ["HeaderIdentity", "Parties", "Stops", "Equipment", "Documents", "Notes"],
    editable: ["Parties", "Stops", "Equipment", "Documents", "Notes"],
    defaultSection: "Parties",
  },
  detail: {
    visible: ["HeaderIdentity", "Parties", "Stops", "Equipment", "Assignment", "Documents", "Notes"],
    editable: ["Parties", "Stops", "Equipment", "Assignment", "Documents", "Notes"],
    defaultSection: "Stops",
  },
  payroll: {
    visible: ["HeaderIdentity", "Assignment", "Settlement", "Documents"],
    editable: [],
    defaultSection: "Settlement",
  },
  audit: {
    visible: ["HeaderIdentity", "Parties", "Stops", "Assignment", "Settlement", "Documents", "AuditTimeline"],
    editable: [],
    defaultSection: "AuditTimeline",
  },
};

/** Single object snapshot for all editable load fields (hydrate + persist via buildLoadPersistPayload). */
export interface WorkspaceDraftFields {
  status: string;
  loadNumber: string;
  brokerId: number | null;
  brokerContactId: number | null;
  brokerNameSnapshot: string;
  brokerContactNameSnapshot: string;
  brokerContactPhoneSnapshot: string;
  brokerContactExtensionSnapshot: string;
  brokerContactEmailSnapshot: string;
  brokerLoadReference: string;
  loadReferences: LoadDocumentParseReference[];
  freightMode: string;
  equipmentType: string;
  trailerType: string;
  trailerSize: string;
  commodity: string;
  estimatedWeight: string;
  hazmat: "unset" | "yes" | "no";
  temperatureRequirement: string;
  palletCaseCount: string;
  rate: string;
  customerRate: string;
  miles: string;
  driverId: number | null;
  truckId: number | null;
  trailerAssetId: number | null;
  customsBrokerId: number | null;
  internalNotes: string;
  draftStops: DraftStop[];
}

export function initialWorkspaceFieldsManual(): WorkspaceDraftFields {
  return {
    status: "draft",
    loadNumber: "",
    brokerId: null,
    brokerContactId: null,
    brokerNameSnapshot: "",
    brokerContactNameSnapshot: "",
    brokerContactPhoneSnapshot: "",
    brokerContactExtensionSnapshot: "",
    brokerContactEmailSnapshot: "",
    brokerLoadReference: "",
    loadReferences: [],
    freightMode: "",
    equipmentType: "",
    trailerType: "",
    trailerSize: "",
    commodity: "",
    estimatedWeight: "",
    hazmat: "unset",
    temperatureRequirement: "",
    palletCaseCount: "",
    rate: "",
    customerRate: "",
    miles: "",
    driverId: null,
    truckId: null,
    trailerAssetId: null,
    customsBrokerId: null,
    internalNotes: "",
    draftStops: initialManualCreateStops(),
  };
}

/** Serialize workspace form state for load_workspace_drafts.draft_json (camelCase). */
export function buildWorkspaceDraftJson(
  params: LoadPersistParams & { status?: string },
): Record<string, unknown> {
  return {
    status: params.status ?? "draft",
    loadNumber: params.loadNumber,
    brokerId: params.brokerId,
    brokerContactId: params.brokerContactId,
    brokerNameSnapshot: params.brokerNameSnapshot,
    brokerContactNameSnapshot: params.brokerContactNameSnapshot,
    brokerContactPhoneSnapshot: params.brokerContactPhoneSnapshot,
    brokerContactExtensionSnapshot: params.brokerContactExtensionSnapshot,
    brokerContactEmailSnapshot: params.brokerContactEmailSnapshot,
    brokerLoadReference: params.brokerLoadReference,
    loadReferences: params.loadReferences ?? [],
    freightMode: params.mode,
    equipmentType: params.equipmentType,
    trailerType: params.trailerType,
    trailerSize: params.trailerSize,
    commodity: params.commodity,
    estimatedWeight: params.estimatedWeight,
    hazmat: params.hazmat,
    temperatureRequirement: params.temperatureRequirement,
    palletCaseCount: params.palletCaseCount,
    rate: params.rate,
    customerRate: params.customerRate.trim() === "" ? params.rate.trim() : params.customerRate,
    miles: params.miles,
    /** Draft-only proposed trip assignment — not operational Load assignment. */
    driverId: params.driverId ?? null,
    truckId: params.truckId ?? null,
    trailerAssetId: params.trailerAssetId ?? null,
    customsBrokerId: params.customsBrokerId,
    internalNotes: params.internalNotes,
    draftStops: params.draftStops.map((stop, index) => {
      const { _key, load_id: _loadId, ...rest } = stop;
      return { ...rest, sequence: rest.sequence ?? index };
    }),
  };
}

function draftStopsFromDraftJson(raw: unknown): DraftStop[] {
  if (!Array.isArray(raw) || raw.length === 0) {
    return initialManualCreateStops();
  }
  return raw.map((entry, index) => {
    const row = (entry && typeof entry === "object" ? entry : {}) as Record<string, unknown>;
    const stopType = String(row.stop_type ?? row.stopType ?? "PICKUP");
    const seq = typeof row.sequence === "number" ? row.sequence : index;
    const id = typeof row.id === "number" ? row.id : 0;
    return {
      id,
      load_id: 0,
      stop_type: stopType,
      sequence: seq,
      facility_name: (row.facility_name ?? row.facilityName ?? null) as string | null,
      street: (row.street ?? null) as string | null,
      city: (row.city ?? null) as string | null,
      state_or_province: (row.state_or_province ?? row.stateOrProvince ?? null) as string | null,
      postal_code: (row.postal_code ?? row.postalCode ?? null) as string | null,
      country: (row.country ?? null) as string | null,
      reference_number: (row.reference_number ?? row.referenceNumber ?? null) as string | null,
      appointment_type: (row.appointment_type ?? row.appointmentType ?? null) as string | null,
      appointment_date: (row.appointment_date ?? row.appointmentDate ?? null) as string | null,
      appointment_time_text: (row.appointment_time_text ?? row.appointmentTimeText ?? null) as string | null,
      notes: (row.notes ?? null) as string | null,
      commodity_notes: (row.commodity_notes ?? row.commodityNotes ?? null) as string | null,
      _key: `draft-stop-${index}-${id}`,
    };
  });
}

function draftProposedAssignmentId(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null;
}

/** Hydrate workspace field snapshot from persisted draft_json. */
export function workspaceFieldsFromDraftJson(j: Record<string, unknown>): WorkspaceDraftFields {
  const hazmatRaw = j.hazmat;
  let hazmat: "unset" | "yes" | "no" = "unset";
  if (hazmatRaw === true || hazmatRaw === "yes") hazmat = "yes";
  else if (hazmatRaw === false || hazmatRaw === "no") hazmat = "no";

  return {
    status: String(j.status ?? "draft"),
    loadNumber: String(j.loadNumber ?? j.load_number ?? ""),
    brokerId: (j.brokerId ?? j.broker_id ?? null) as number | null,
    brokerContactId: (j.brokerContactId ?? j.broker_contact_id ?? null) as number | null,
    brokerNameSnapshot: String(j.brokerNameSnapshot ?? j.broker_name_snapshot ?? ""),
    brokerContactNameSnapshot: String(
      j.brokerContactNameSnapshot ?? j.broker_contact_name_snapshot ?? "",
    ),
    brokerContactPhoneSnapshot: String(
      j.brokerContactPhoneSnapshot ?? j.broker_contact_phone_snapshot ?? "",
    ),
    brokerContactExtensionSnapshot: String(
      j.brokerContactExtensionSnapshot ?? j.broker_contact_extension_snapshot ?? "",
    ),
    brokerContactEmailSnapshot: String(
      j.brokerContactEmailSnapshot ?? j.broker_contact_email_snapshot ?? "",
    ),
    brokerLoadReference: String(j.brokerLoadReference ?? j.broker_load_reference ?? ""),
    loadReferences: Array.isArray(j.loadReferences)
      ? (j.loadReferences as LoadDocumentParseReference[])
      : Array.isArray(j.references)
        ? (j.references as LoadDocumentParseReference[])
        : [],
    freightMode: String(j.freightMode ?? j.mode ?? ""),
    equipmentType: String(j.equipmentType ?? j.equipment_type ?? ""),
    trailerType: String(j.trailerType ?? j.trailer_type ?? ""),
    trailerSize: String(j.trailerSize ?? j.trailer_size ?? ""),
    commodity: String(j.commodity ?? ""),
    estimatedWeight: String(j.estimatedWeight ?? j.estimated_weight ?? ""),
    hazmat,
    temperatureRequirement: String(j.temperatureRequirement ?? j.temperature_requirement ?? ""),
    palletCaseCount: String(j.palletCaseCount ?? j.pallet_case_count ?? ""),
    rate: String(j.rate ?? ""),
    customerRate: String(j.customerRate ?? j.customer_rate ?? ""),
    miles: String(j.miles ?? ""),
    driverId: draftProposedAssignmentId(j.driverId ?? j.driver_id),
    truckId: draftProposedAssignmentId(j.truckId ?? j.truck_id),
    trailerAssetId: draftProposedAssignmentId(
      j.trailerAssetId ?? j.trailer_asset_id ?? j.trailerId ?? j.trailer_id,
    ),
    customsBrokerId: (j.customsBrokerId ?? j.customs_broker_id ?? null) as number | null,
    internalNotes: String(j.internalNotes ?? j.internal_notes ?? ""),
    draftStops: draftStopsFromDraftJson(j.draftStops ?? j.stops),
  };
}

export function workspaceFieldsFromLoad(l: Load): WorkspaceDraftFields {
  return {
    status: l.status,
    loadNumber: l.load_number || "",
    brokerId: l.broker_id ?? null,
    brokerContactId: l.broker_contact_id ?? null,
    brokerNameSnapshot: l.broker_name_snapshot ?? "",
    brokerContactNameSnapshot: l.broker_contact_name_snapshot ?? "",
    brokerContactPhoneSnapshot: l.broker_contact_phone_snapshot ?? "",
    brokerContactExtensionSnapshot: l.broker_contact_extension_snapshot ?? "",
    brokerContactEmailSnapshot: l.broker_contact_email_snapshot ?? "",
    brokerLoadReference: l.broker_load_reference ?? "",
    loadReferences: Array.isArray(l.references) ? l.references : [],
    freightMode: l.mode ?? "",
    equipmentType: l.equipment_type ?? "",
    trailerType: l.trailer_type ?? "",
    trailerSize: l.trailer_size ?? "",
    commodity: l.commodity ?? "",
    estimatedWeight: l.estimated_weight != null ? String(l.estimated_weight) : "",
    hazmat: l.hazmat_flag === true ? "yes" : l.hazmat_flag === false ? "no" : "unset",
    temperatureRequirement: l.temperature_requirement ?? "",
    palletCaseCount: l.pallet_case_count ?? "",
    rate: l.rate != null ? String(l.rate) : "",
    customerRate: l.customer_rate != null ? String(l.customer_rate) : "",
    miles: l.miles != null ? String(l.miles) : "",
    driverId: l.driver_id ?? null,
    truckId: l.truck_id ?? null,
    trailerAssetId: l.trailer_id ?? null,
    customsBrokerId: l.customs_broker_id ?? null,
    internalNotes: l.internal_notes ?? "",
    draftStops: stopsToDraft(l.stops),
  };
}

export type DraftStop = LoadStop & {
  _key: string;
  /** Parser evidence when stop_type is unresolved (Issue I19). */
  parseStopTypeEvidence?: string | null;
};

/** Proposed values sourced from the intake pipeline for a given email thread.
 *  Only fields that the current backend API actually populates are listed here.
 *  All others are intentionally absent — add them when the backend exposes them. */
export interface IntakeProposedFields {
  /** From InboxThreadListItem.linked_broker_name. The only intake-proposed form field the backend exposes today. */
  brokerNameSnapshot: string | null;
  /** From InboxThreadListItem.pickup_delivery_summary. Display-only context — not wired to any form input. */
  pickupDeliverySummary: string | null;
}

export function emptyIntakeProposed(): IntakeProposedFields {
  return { brokerNameSnapshot: null, pickupDeliverySummary: null };
}

export const sectionTitleClass =
  "text-[10px] font-semibold tracking-[0.75px] uppercase text-gray-500 border-b border-gray-200 pb-2 mb-4";
export const labelClass = "block text-xs font-medium text-gray-600 mb-1";
export const inputClass =
  "w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:ring-indigo-500";
export const grid2 = "grid grid-cols-1 gap-4 sm:grid-cols-2";

/** Load workspace form — condensed card rhythm (TruckERP tokens). */
export const wsSectionCard =
  "rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] overflow-hidden";
export const wsSectionHeader =
  "flex items-center justify-between gap-2 border-b border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-3 py-2";
export const wsSectionTitle =
  "text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--trk-heading)]";
export const wsSectionBody = "px-3 py-2.5";
export const wsSectionMeta = "text-[10px] font-medium text-[var(--trk-text-muted)]";
export const wsLabelClass =
  "block text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)] mb-1";
export const wsInputClass =
  "w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1.5 text-[13px] text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)] focus:border-[var(--trk-heading)] focus:outline-none focus:ring-1 focus:ring-[var(--trk-heading)]/25";
export const wsGrid2 = "grid grid-cols-1 gap-2.5 sm:grid-cols-2";
export const wsGrid3 = "grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3";

/** Header glance for linehaul — bound to the load `rate` field, never a hardcoded label. */
export function formatLinehaulDisplay(rate: string): string | null {
  const t = rate.trim();
  if (!t) return null;
  const n = Number(t.replace(/[$,]/g, ""));
  if (Number.isFinite(n) && t.replace(/[$,]/g, "") !== "") {
    return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
  }
  return t.startsWith("$") ? t : `$${t}`;
}

/** Broker-header chip: trailer/equipment plus temperature from load fields. */
export function formatEquipmentTempChip(
  trailerType: string,
  equipmentType: string,
  temperatureRequirement: string,
): string {
  const equip = trailerType.trim() || equipmentType.trim() || "Equipment";
  const temp = temperatureRequirement.trim();
  return temp ? `${equip} · ${temp}` : `${equip} · No temp set`;
}

export function stopToPayload(s: DraftStop, sequence: number): LoadStopWrite {
  const payload: LoadStopWrite = {
    stop_type: s.stop_type,
    sequence,
    facility_name: s.facility_name?.trim() || null,
    street: s.street?.trim() || null,
    city: s.city?.trim() || null,
    state_or_province: s.state_or_province?.trim() || null,
    postal_code: s.postal_code?.trim() || null,
    country: s.country?.trim() || null,
    reference_number: s.reference_number?.trim() || null,
    appointment_type: s.appointment_type?.trim() || null,
    appointment_date: s.appointment_date?.trim() || null,
    appointment_time_text: s.appointment_time_text?.trim() || null,
    notes: s.notes?.trim() || null,
    commodity_notes: s.commodity_notes?.trim() || null,
  };
  if (s.id != null && s.id > 0) {
    (payload as LoadStopWrite & { id?: number }).id = s.id;
  }
  return payload;
}

export function stopsToDraft(stops: LoadStop[] | null | undefined): DraftStop[] {
  return sortStops(stops).map((s) => ({
    ...s,
    _key: `stop-${s.id}`,
  }));
}

export function newDraftStop(seq: number, stopType: string = "PICKUP"): DraftStop {
  return {
    id: 0,
    load_id: 0,
    stop_type: stopType,
    sequence: seq,
    facility_name: null,
    street: null,
    city: null,
    state_or_province: null,
    postal_code: null,
    country: null,
    reference_number: null,
    appointment_type: null,
    appointment_date: null,
    appointment_time_text: null,
    scheduled_at: null,
    notes: null,
    commodity_notes: null,
    created_at: null,
    updated_at: null,
    _key: `new-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
  };
}

/** Default pickup + delivery for manual create. */
export function initialManualCreateStops(): DraftStop[] {
  return [newDraftStop(0, "PICKUP"), newDraftStop(1, "DELIVERY")];
}

/** Options for matching a form field to a line in extracted RC / internal_notes text. */
export type DocFocusOpts = {
  /** Primary field value — highest priority; matching uses normalized variants. */
  primaryValue?: string;
  /** Additional values (e.g. formatted + raw) beyond `primaryValue`. */
  extraValues?: string[];
  /** Context keywords — tie-breakers only; not used alone when `primaryValue` is set. */
  hintTokens?: string[];
  /** Legacy combined list; prefer `primaryValue` + `hintTokens`. */
  tokens?: string[];
  fallbackToken?: string;
  /** Lines containing these start the Nth section (0-based `sectionIndex`). */
  sectionStartMatchers?: string[];
  /** First line after the section start that contains any of these ends the window (exclusive). */
  sectionEndMatchers?: string[];
  /** @deprecated Use sectionStartMatchers */
  sectionMatchers?: string[];
  sectionIndex?: number;
};

const DOC_FOCUS_MIN_PRIMARY_SCORE = 28;
const DOC_FOCUS_MIN_HINT_ONLY_SCORE = 12;

const DOC_FOCUS_GENERIC_TOKENS = new Set(
  [
    "rate",
    "linehaul",
    "ref",
    "reference",
    "pickup",
    "pick up",
    "delivery",
    "deliver",
    "drop",
    "address",
    "location",
    "equipment",
    "trailer",
    "commodity",
    "weight",
    "lbs",
    "lb",
    "appointment",
    "appt",
    "appt.",
    "window",
    "fcfs",
    "origin",
    "shipper",
    "consignee",
    "dest",
    "unload",
    "broker",
    "carrier",
    "contact",
    "phone",
    "email",
    "miles",
    "mile",
    "total",
    "amount",
    "$",
    "po",
    "bol",
    "order",
    "product",
    "freight",
    "description",
    "cargo",
    "sku",
    "pounds",
    "gross",
    "hazmat",
    "temperature",
    "temp",
    "pallet",
    "case",
    "mode",
    "van",
    "reefer",
    "flatbed",
    "dry van",
    "step deck",
    "53",
    "confirmation",
    "rate con",
  ].map((s) => s.toLowerCase()),
);

function isDocFocusValueToken(token: string): boolean {
  const t = token.trim();
  if (!t) return false;
  const lower = t.toLowerCase();
  if (DOC_FOCUS_GENERIC_TOKENS.has(lower)) return false;
  if (/\d/.test(t)) return true;
  return t.length >= 3;
}

/** Collapse whitespace and lowercase for substring checks. */
export function normalizeDocFocusLine(text: string): string {
  return text.trim().replace(/\s+/g, " ").toLowerCase();
}

function digitsOnlyDocFocus(text: string): string {
  return text.replace(/\D/g, "");
}

/** Build search needles for a single field value (currency, dates, phone digits). */
export function expandDocFocusVariants(raw: string): string[] {
  const t = raw.trim();
  if (!t) return [];
  const out = new Set<string>();
  out.add(t);
  out.add(t.toLowerCase());
  const collapsed = t.replace(/\s+/g, " ");
  if (collapsed !== t) out.add(collapsed);

  const iso = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) {
    const y = iso[1];
    const m = iso[2];
    const d = iso[3];
    const mi = String(parseInt(m, 10));
    const di = String(parseInt(d, 10));
    out.add(`${m}/${d}/${y}`);
    out.add(`${mi}/${di}/${y}`);
    out.add(`${m}-${d}-${y}`);
    out.add(`${mi}-${di}-${y}`);
  }

  const slashDate = t.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})/);
  if (slashDate) {
    const [, mm, dd, yy] = slashDate;
    const y4 = yy.length === 2 ? `20${yy}` : yy;
    out.add(`${y4}-${mm.padStart(2, "0")}-${dd.padStart(2, "0")}`);
    out.add(`${mm}/${dd}/${y4}`);
  }

  const moneyDigits = t.replace(/[^\d.]/g, "");
  if (moneyDigits && /^\d/.test(moneyDigits)) {
    out.add(moneyDigits);
    const num = Number.parseFloat(moneyDigits);
    if (Number.isFinite(num)) {
      out.add(String(num));
      if (Number.isInteger(num)) out.add(String(Math.trunc(num)));
      const withCommas = num.toLocaleString("en-US", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      });
      out.add(withCommas);
      out.add(`$${withCommas}`);
      out.add(num.toFixed(2));
      out.add(`$${num.toFixed(2)}`);
    }
  }

  const phoneDigits = digitsOnlyDocFocus(t);
  if (phoneDigits.length >= 7) {
    out.add(phoneDigits);
    if (phoneDigits.length === 10) {
      out.add(`(${phoneDigits.slice(0, 3)}) ${phoneDigits.slice(3, 6)}-${phoneDigits.slice(6)}`);
    }
  }

  const weightDigits = digitsOnlyDocFocus(t);
  if (weightDigits.length >= 3 && weightDigits !== phoneDigits) out.add(weightDigits);

  return [...out].filter((s) => s.length >= 2 || /\d/.test(s));
}

function resolveDocFocusNeedles(opts: DocFocusOpts): { primaryNeedles: string[]; hintTokens: string[] } {
  const hintTokens = [...(opts.hintTokens ?? [])];
  const primaryNeedles: string[] = [];

  const pushPrimary = (v: string) => {
    for (const needle of expandDocFocusVariants(v)) {
      if (!primaryNeedles.includes(needle)) primaryNeedles.push(needle);
    }
  };

  if (opts.primaryValue?.trim()) pushPrimary(opts.primaryValue);
  for (const extra of opts.extraValues ?? []) {
    if (extra?.trim()) pushPrimary(extra);
  }

  const legacy = (opts.tokens ?? []).map((t) => (t || "").trim()).filter(Boolean);
  if (!primaryNeedles.length && legacy.length) {
    for (const t of legacy) {
      if (isDocFocusValueToken(t)) pushPrimary(t);
      else hintTokens.push(t);
    }
  } else if (legacy.length) {
    for (const t of legacy) {
      if (!isDocFocusValueToken(t)) hintTokens.push(t);
    }
  }

  if (!hintTokens.length && opts.fallbackToken?.trim() && !primaryNeedles.length) {
    if (isDocFocusValueToken(opts.fallbackToken)) pushPrimary(opts.fallbackToken);
    else hintTokens.push(opts.fallbackToken.trim());
  }

  return { primaryNeedles, hintTokens };
}

function lineMatchesPrimaryNeedle(line: string, needle: string): { hit: boolean; score: number } {
  const normLine = normalizeDocFocusLine(line);
  const normNeedle = normalizeDocFocusLine(needle);
  if (!normNeedle) return { hit: false, score: 0 };
  if (normLine === normNeedle) return { hit: true, score: 100 };
  if (normLine.includes(normNeedle)) {
    return { hit: true, score: 42 + Math.min(28, normNeedle.length) };
  }
  const lineDigits = digitsOnlyDocFocus(line);
  const needleDigits = digitsOnlyDocFocus(needle);
  if (needleDigits.length >= 3 && lineDigits.includes(needleDigits)) {
    return { hit: true, score: 36 + Math.min(20, needleDigits.length) };
  }
  return { hit: false, score: 0 };
}

function scoreDocLineForFocus(
  lineRaw: string,
  primaryNeedles: string[],
  hintTokens: string[],
): { score: number; primaryHit: boolean } {
  const line = lineRaw;
  if (!normalizeDocFocusLine(line)) return { score: 0, primaryHit: false };

  let score = 0;
  let primaryHit = false;
  for (const needle of primaryNeedles) {
    const m = lineMatchesPrimaryNeedle(line, needle);
    if (m.hit) {
      primaryHit = true;
      score = Math.max(score, m.score);
    }
  }
  if (primaryHit) {
    for (const h of hintTokens) {
      const nh = normalizeDocFocusLine(h);
      if (nh && normalizeDocFocusLine(line).includes(nh)) score += 3;
    }
    return { score, primaryHit };
  }
  for (const h of hintTokens) {
    const nh = normalizeDocFocusLine(h);
    if (nh && normalizeDocFocusLine(line).includes(nh)) score += 5;
  }
  return { score, primaryHit: false };
}

function docFocusFieldOpts(
  primaryValue: string,
  hintTokens: string[],
  section?: Partial<DocFocusOpts>,
): DocFocusOpts {
  return {
    primaryValue,
    hintTokens,
    ...section,
  };
}

function docLineSectionBounds(
  docLines: string[],
  startMatchers: string[],
  endMatchers: string[],
  sectionIndex: number,
): { start: number; end: number } | null {
  if (!startMatchers.length || sectionIndex < 0) return null;
  const starts: number[] = [];
  for (let i = 0; i < docLines.length; i++) {
    const line = docLines[i].toLowerCase();
    if (startMatchers.some((m) => line.includes(m.toLowerCase()))) starts.push(i);
  }
  if (!starts.length) return null;
  const start = starts[Math.min(sectionIndex, starts.length - 1)];
  let end = docLines.length;
  if (endMatchers.length) {
    for (let i = start + 1; i < docLines.length; i++) {
      const line = docLines[i].toLowerCase();
      if (endMatchers.some((m) => line.includes(m.toLowerCase()))) {
        end = i;
        break;
      }
    }
  }
  return { start, end };
}

type DocFocusCandidate = { idx: number; score: number; primaryHit: boolean };

function pickBestDocFocusCandidate(
  docLines: string[],
  start: number,
  end: number,
  primaryNeedles: string[],
  hintTokens: string[],
  sectionBonus: boolean,
): DocFocusCandidate | null {
  let best: DocFocusCandidate | null = null;
  for (let i = start; i < end; i++) {
    const { score, primaryHit } = scoreDocLineForFocus(docLines[i], primaryNeedles, hintTokens);
    let total = score;
    if (sectionBonus && score > 0) total += 4;
    if (total <= 0) continue;
    if (!best || total > best.score || (total === best.score && primaryHit && !best.primaryHit)) {
      best = { idx: i, score: total, primaryHit };
    }
  }
  return best;
}

/** Pick the best line index in extracted document text for field-driven verification focus. */
export function findBestDocLineIndex(docLines: string[], opts: DocFocusOpts): number {
  if (!docLines.length) return -1;
  const { primaryNeedles, hintTokens } = resolveDocFocusNeedles(opts);
  const hasPrimary = primaryNeedles.length > 0;

  const startMatchers = opts.sectionStartMatchers?.length
    ? opts.sectionStartMatchers
    : opts.sectionMatchers;
  const bounds =
    startMatchers?.length && opts.sectionIndex != null
      ? docLineSectionBounds(docLines, startMatchers, opts.sectionEndMatchers ?? [], opts.sectionIndex)
      : null;

  const tryPick = (start: number, end: number, sectionBonus: boolean) =>
    pickBestDocFocusCandidate(docLines, start, end, primaryNeedles, hintTokens, sectionBonus);

  let candidate =
    bounds != null
      ? tryPick(bounds.start, bounds.end, true)
      : tryPick(0, docLines.length, false);

  if (hasPrimary && candidate && !candidate.primaryHit) {
    candidate = null;
  }

  if (hasPrimary && (!candidate || !candidate.primaryHit)) {
    const full = tryPick(0, docLines.length, false);
    if (full?.primaryHit) candidate = full;
  }

  if (!candidate) return -1;

  if (hasPrimary) {
    return candidate.primaryHit && candidate.score >= DOC_FOCUS_MIN_PRIMARY_SCORE ? candidate.idx : -1;
  }

  return candidate.score >= DOC_FOCUS_MIN_HINT_ONLY_SCORE ? candidate.idx : -1;
}

/** Run doc focus on focus and click (click covers re-selecting an already-focused field). */
export function bindDocFocus(
  focusDoc: (opts: DocFocusOpts) => void,
  opts: DocFocusOpts,
): { onFocus: () => void; onClick: () => void } {
  const run = () => focusDoc(opts);
  return { onFocus: run, onClick: run };
}

export function docFocusSectionBoundsForStop(stop: DraftStop): {
  sectionStartMatchers: string[];
  sectionEndMatchers: string[];
} | undefined {
  const type = (stop.stop_type || "").toUpperCase();
  const isPickup = type === "PICKUP";
  const isDelivery = type === "DELIVERY" || type === "DROP";
  if (isPickup) {
    return {
      sectionStartMatchers: ["pick up", "pickup", "pu "],
      sectionEndMatchers: ["delivery", "deliver", "drop", "consignee"],
    };
  }
  if (isDelivery) {
    return { sectionStartMatchers: ["delivery", "deliver", "drop"], sectionEndMatchers: ["pick up", "pickup"] };
  }
  return undefined;
}

function docFocusStopSectionOpts(stop: DraftStop, sectionIndex: number): Partial<DocFocusOpts> {
  const bounds = docFocusSectionBoundsForStop(stop);
  if (!bounds) return {};
  return { ...bounds, sectionIndex };
}

function stopTypeHints(stop: DraftStop): string[] {
  const type = (stop.stop_type || "").toUpperCase();
  const isPickup = type === "PICKUP";
  const isDelivery = type === "DELIVERY" || type === "DROP";
  if (isPickup) return ["pickup", "pick up", "shipper", "origin"];
  if (isDelivery) return ["delivery", "deliver", "consignee", "receiver"];
  return [];
}

export function docFocusForBroker(brokerName: string): DocFocusOpts {
  const name = brokerName.trim();
  return docFocusFieldOpts(name, ["broker", "carrier", "logistics", "mc", "dot"]);
}

export function docFocusForBrokerLoadReference(brokerLoadReference: string): DocFocusOpts {
  const ref = brokerLoadReference.trim();
  return docFocusFieldOpts(ref, ["load #", "load no", "reference", "order #", "bol"]);
}

export function docFocusForBrokerContactName(name: string): DocFocusOpts {
  return docFocusFieldOpts(name.trim(), ["contact", "dispatcher", "dispatch"]);
}

export function docFocusForBrokerContactPhone(phone: string, extension: string): DocFocusOpts {
  const p = phone.trim();
  const ext = extension.trim();
  return docFocusFieldOpts(p, ["phone", "tel", "fax", ...(ext ? [`ext ${ext}`, `x${ext}`] : [])]);
}

export function docFocusForBrokerContactEmail(email: string): DocFocusOpts {
  return docFocusFieldOpts(email.trim(), ["email", "e-mail", "@"]);
}

/** @deprecated Use field-specific broker contact helpers */
export function docFocusForBrokerContact(parts: {
  name: string;
  phone: string;
  email: string;
}): DocFocusOpts {
  const name = parts.name.trim();
  const phone = parts.phone.trim();
  const email = parts.email.trim();
  const primary = name || phone || email;
  return docFocusFieldOpts(primary, ["contact", "phone", "email", "dispatcher"]);
}

export function docFocusForMoneyField(value: string, kind: "linehaul" | "customer" | "miles"): DocFocusOpts {
  const v = value.trim();
  if (kind === "miles") {
    return docFocusFieldOpts(v, ["miles", "mile", "mi", "distance"]);
  }
  return docFocusFieldOpts(v, ["rate", "linehaul", "line haul", "total", "amount", "pay"]);
}

export function docFocusForFreightHints(fieldValue: string, hints: string[]): DocFocusOpts {
  return docFocusFieldOpts(fieldValue.trim(), hints);
}

export function docFocusForStopFacility(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  return docFocusFieldOpts((stop.facility_name ?? "").trim(), stopTypeHints(stop), {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function docFocusForStopStreet(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  return docFocusFieldOpts((stop.street ?? "").trim(), ["st", "street", "ave", "road", "rd", "blvd"], {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function docFocusForStopCity(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  return docFocusFieldOpts((stop.city ?? "").trim(), stopTypeHints(stop), {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function docFocusForStopState(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  const state = (stop.state_or_province ?? "").trim();
  return docFocusFieldOpts(state, stopTypeHints(stop), {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function docFocusForStopPostal(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  return docFocusFieldOpts((stop.postal_code ?? "").trim(), ["zip", "postal"], {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function docFocusForStopCountry(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  return docFocusFieldOpts((stop.country ?? "").trim(), ["country"], {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

/** Combined address search — avoid for per-field verification; use stop field helpers. */
export function docFocusForStopAddress(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  return docFocusForStopStreet(stop, sectionIndex);
}

export function docFocusForStopAppointmentDate(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  const raw = (stop.appointment_date ?? "").trim();
  return docFocusFieldOpts(raw, ["appt", "appointment", "date", ...stopTypeHints(stop)], {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function docFocusForStopAppointmentTime(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  const raw = (stop.appointment_time_text ?? "").trim();
  return docFocusFieldOpts(raw, ["appt", "appointment", "time", "fcfs", "window", ...stopTypeHints(stop)], {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function docFocusForStopAppointmentType(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  const raw = (stop.appointment_type ?? "").trim();
  return docFocusFieldOpts(raw, ["appt", "appointment", "fcfs", "strict", "window"], {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

/** @deprecated Use date/time/type-specific helpers */
export function docFocusForStopAppointment(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  return docFocusForStopAppointmentDate(stop, sectionIndex);
}

export function docFocusForStopReference(stop: DraftStop, sectionIndex = 0): DocFocusOpts {
  const ref = (stop.reference_number ?? "").trim();
  const type = (stop.stop_type || "").toUpperCase();
  const isPickup = type === "PICKUP";
  const isDelivery = type === "DELIVERY" || type === "DROP";
  return docFocusFieldOpts(ref, [
    ...(isPickup ? ["pickup ref", "shipper ref"] : []),
    ...(isDelivery ? ["delivery ref", "receiver ref"] : []),
    "po",
    "reference",
    "ref",
    "bol",
  ], {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function docFocusForStopNotes(stop: DraftStop, sectionIndex = 0, notes: string): DocFocusOpts {
  const text = notes.trim();
  return docFocusFieldOpts(text, ["notes", "instruction", "special", ...stopTypeHints(stop)], {
    ...docFocusStopSectionOpts(stop, sectionIndex),
  });
}

export function buildVerificationTabIndexMap(sortedStops: DraftStop[]): Map<string, number> {
  const map = new Map<string, number>();
  let n = 0;
  const next = () => {
    n += 1;
    return n;
  };

  map.set("brokerLoadReference", next());
  map.set("loadNumber", next());

  const appendStopKeys = (stop: DraftStop) => {
    const k = stop._key;
    map.set(`${k}::facility`, next());
    map.set(`${k}::street`, next());
    map.set(`${k}::city`, next());
    map.set(`${k}::state`, next());
    map.set(`${k}::postal`, next());
    map.set(`${k}::country`, next());
    map.set(`${k}::apptType`, next());
    map.set(`${k}::apptDate`, next());
    map.set(`${k}::apptTime`, next());
    map.set(`${k}::reference`, next());
  };

  const pickup = sortedStops.find((s) => (s.stop_type || "").toUpperCase() === "PICKUP");
  if (pickup) appendStopKeys(pickup);

  const delivery = sortedStops.find((s) => {
    const u = (s.stop_type || "").toUpperCase();
    return u === "DELIVERY" || u === "DROP";
  });
  if (delivery) appendStopKeys(delivery);

  map.set("equipmentType", next());
  map.set("trailerType", next());
  map.set("commodity", next());
  map.set("estimatedWeight", next());
  map.set("rate", next());

  return map;
}

function isManualPickupDeliveryPair(a: DraftStop, b: DraftStop): boolean {
  const u = (x: string) => (x || "").toUpperCase();
  const t0 = u(a.stop_type);
  const t1 = u(b.stop_type);
  return (
    (t0 === "PICKUP" && (t1 === "DELIVERY" || t1 === "DROP")) ||
    (t1 === "PICKUP" && (t0 === "DELIVERY" || t0 === "DROP"))
  );
}

/** Assign unique 0-based sequence values in current sort order. */
export function normalizeDraftStopSequences<T extends { sequence?: number }>(stops: T[]): T[] {
  return stops.map((s, idx) => ({ ...s, sequence: idx }));
}

/** Swap one stop up/down in route order; renumbers sequences so duplicate values cannot break reorder. */
export function reorderDraftStopsByKey<T extends { _key: string; sequence?: number }>(
  rows: T[],
  key: string,
  dir: -1 | 1,
): T[] {
  const sorted = [...rows].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
  const i = sorted.findIndex((r) => r._key === key);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= sorted.length) return rows;
  const reordered = [...sorted];
  const tmp = reordered[i];
  reordered[i] = reordered[j];
  reordered[j] = tmp;
  return normalizeDraftStopSequences(reordered);
}

/**
 * Second line of defense: when more than two rows exist, drop stop rows with no useful
 * identity, **except** the leading PICKUP + DELIVERY (or DELIVERY + PICKUP) pair when
 * present — that pair is the manual template and may have empty address fields. Rows
 * with real location/reference data are always kept.
 */
export function selectDraftStopsForPersist(draftStops: DraftStop[]): DraftStop[] {
  const sorted = [...draftStops].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
  if (sorted.length <= 2) return sorted;

  const leadIsManualPair =
    sorted.length >= 2 && isManualPickupDeliveryPair(sorted[0], sorted[1]);

  return sorted.filter((s, index) => {
    if (hasUsefulStopIdentity(s)) return true;
    if (leadIsManualPair && (index === 0 || index === 1)) return true;
    return false;
  });
}

export type LoadPersistParams = {
  loadNumber: string;
  brokerId: number | null;
  brokerContactId: number | null;
  brokerNameSnapshot: string;
  brokerContactNameSnapshot: string;
  brokerContactPhoneSnapshot: string;
  brokerContactExtensionSnapshot: string;
  brokerContactEmailSnapshot: string;
  brokerLoadReference: string;
  loadReferences?: LoadDocumentParseReference[];
  mode: string;
  equipmentType: string;
  trailerType: string;
  trailerSize: string;
  commodity: string;
  estimatedWeight: string;
  hazmat: "unset" | "yes" | "no";
  temperatureRequirement: string;
  palletCaseCount: string;
  rate: string;
  customerRate: string;
  miles: string;
  /** Draft-only proposed trip assignment (draft_json); never sent on Load PATCH. */
  driverId?: number | null;
  truckId?: number | null;
  trailerAssetId?: number | null;
  customsBrokerId: number | null;
  internalNotes: string;
  draftStops: DraftStop[];
};

/**
 * Commercial Save body for PATCH. Never carries `status` or Load `driver_id` / `truck_id` / `trailer_id`:
 * readiness moves only via Mark ready, and equipment / lifecycle belong to the Trip.
 */
export function buildLoadPersistPayload(params: LoadPersistParams): LoadWritePayload {
  const sorted = selectDraftStopsForPersist(params.draftStops);
  const stopsPayload = sorted.map((s, i) => stopToPayload(s, i));
  const estW = params.estimatedWeight.trim();
  const rateN = params.rate.trim();
  const crN = params.customerRate.trim() || rateN;
  const milesN = params.miles.trim();

  return {
    broker_id: params.brokerId,
    broker_contact_id: params.brokerContactId,
    broker_name_snapshot: params.brokerNameSnapshot.trim() || null,
    broker_contact_name_snapshot: params.brokerContactNameSnapshot.trim() || null,
    broker_contact_phone_snapshot: params.brokerContactPhoneSnapshot.trim() || null,
    broker_contact_extension_snapshot: params.brokerContactExtensionSnapshot.trim() || null,
    broker_contact_email_snapshot: params.brokerContactEmailSnapshot.trim() || null,
    broker_load_reference: params.brokerLoadReference.trim() || null,
    references: params.loadReferences ?? [],
    mode: params.mode.trim() || null,
    equipment_type: params.equipmentType.trim() || null,
    trailer_type: params.trailerType.trim() || null,
    trailer_size: params.trailerSize.trim() || null,
    commodity: params.commodity.trim() || null,
    estimated_weight: estW === "" ? null : Math.max(0, parseInt(estW, 10) || 0),
    hazmat_flag: params.hazmat === "unset" ? null : params.hazmat === "yes",
    temperature_requirement: params.temperatureRequirement.trim() || null,
    pallet_case_count: params.palletCaseCount.trim() || null,
    rate: rateN === "" ? null : Math.max(0, parseFloat(rateN)),
    customer_rate: crN === "" ? null : Math.max(0, parseFloat(crN)),
    miles: milesN === "" ? null : Math.max(0, parseInt(milesN, 10) || 0),
    customs_broker_id: params.customsBrokerId,
    internal_notes: params.internalNotes.trim() || null,
    stops: stopsPayload,
  };
}

/** POST body for a new Load: commercial fields plus `status: "draft"` (the only status create accepts). */
export function buildLoadCreatePayload(params: LoadPersistParams): LoadWritePayload {
  return { ...buildLoadPersistPayload(params), status: "draft" };
}

/**
 * Stable JSON signature of the persist payload as derived from a server `Load` row.
 * Used to detect local edits vs last server-aligned baseline (optimistic concurrency on the client).
 */
export function baselineSignatureFromLoad(l: Load): string {
  let hazmat: "unset" | "yes" | "no" = "unset";
  if (l.hazmat_flag === true) hazmat = "yes";
  else if (l.hazmat_flag === false) hazmat = "no";
  const payload = buildLoadPersistPayload({
    loadNumber: l.load_number || "",
    brokerId: l.broker_id ?? null,
    brokerContactId: l.broker_contact_id ?? null,
    brokerNameSnapshot: l.broker_name_snapshot ?? "",
    brokerContactNameSnapshot: l.broker_contact_name_snapshot ?? "",
    brokerContactPhoneSnapshot: l.broker_contact_phone_snapshot ?? "",
    brokerContactExtensionSnapshot: l.broker_contact_extension_snapshot ?? "",
    brokerContactEmailSnapshot: l.broker_contact_email_snapshot ?? "",
    brokerLoadReference: l.broker_load_reference ?? "",
    loadReferences: Array.isArray(l.references) ? l.references : [],
    mode: l.mode ?? "",
    equipmentType: l.equipment_type ?? "",
    trailerType: l.trailer_type ?? "",
    trailerSize: l.trailer_size ?? "",
    commodity: l.commodity ?? "",
    estimatedWeight: l.estimated_weight != null ? String(l.estimated_weight) : "",
    hazmat,
    temperatureRequirement: l.temperature_requirement ?? "",
    palletCaseCount: l.pallet_case_count ?? "",
    rate: l.rate != null ? String(l.rate) : "",
    customerRate: l.customer_rate != null ? String(l.customer_rate) : "",
    miles: l.miles != null ? String(l.miles) : "",
    customsBrokerId: l.customs_broker_id ?? null,
    internalNotes: l.internal_notes ?? "",
    draftStops: stopsToDraft(l.stops),
  });
  return JSON.stringify(payload);
}

/** Maps `WorkspaceDraftFields` into the existing persist payload shape (single call site for saves). */
export function buildLoadPersistPayloadFromWorkspaceFields(f: WorkspaceDraftFields): LoadWritePayload {
  return buildLoadPersistPayload({
    loadNumber: f.loadNumber,
    brokerId: f.brokerId,
    brokerContactId: f.brokerContactId,
    brokerNameSnapshot: f.brokerNameSnapshot,
    brokerContactNameSnapshot: f.brokerContactNameSnapshot,
    brokerContactPhoneSnapshot: f.brokerContactPhoneSnapshot,
    brokerContactExtensionSnapshot: f.brokerContactExtensionSnapshot,
    brokerContactEmailSnapshot: f.brokerContactEmailSnapshot,
    brokerLoadReference: f.brokerLoadReference,
    loadReferences: f.loadReferences,
    mode: f.freightMode,
    equipmentType: f.equipmentType,
    trailerType: f.trailerType,
    trailerSize: f.trailerSize,
    commodity: f.commodity,
    estimatedWeight: f.estimatedWeight,
    hazmat: f.hazmat,
    temperatureRequirement: f.temperatureRequirement,
    palletCaseCount: f.palletCaseCount,
    rate: f.rate,
    customerRate: f.customerRate,
    miles: f.miles,
    customsBrokerId: f.customsBrokerId,
    internalNotes: f.internalNotes,
    draftStops: f.draftStops,
  });
}
