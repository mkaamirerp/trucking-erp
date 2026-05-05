/**
 * Shared helpers and UI tokens for the canonical load workspace (create + edit).
 */
import type { Load, LoadStop, LoadStopWrite, LoadWritePayload } from "@/api";
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

export const LOAD_STATUSES = [
  "draft",
  "ready",
  "unassigned",
  "assigned",
  "dispatched",
  "arrived_pickup",
  "in_transit",
  "arrived_delivery",
  "delivered",
  "issue_hold",
] as const;

export type DraftStop = LoadStop & { _key: string };

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

/** Load workspace form — compact card rhythm (light theme, mockup-inspired hierarchy). */
export const wsSectionCard = "rounded-lg border border-[var(--trk-border)] bg-[#1a1e2a] shadow-sm overflow-hidden";
export const wsSectionHeader =
  "flex items-center justify-between gap-2 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3.5 py-2";
export const wsSectionTitle = "text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--trk-text-muted)]";
export const wsSectionBody = "px-3.5 py-3";
export const wsSectionMeta = "text-[10px] font-medium text-[var(--trk-text-muted)]";
export const wsLabelClass =
  "block text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)] mb-1";
export const wsInputClass =
  "w-full rounded-md border border-[var(--trk-border)] bg-[#1a1e2a] px-2.5 py-1.5 text-sm text-[var(--trk-text)] shadow-sm placeholder:text-[var(--trk-text-muted)] focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500/25";
export const wsGrid2 = "grid grid-cols-1 gap-2.5 sm:grid-cols-2";
export const wsGrid3 = "grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3";

export function stopToPayload(s: DraftStop, sequence: number): LoadStopWrite {
  return {
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

export function docFocusForStopAddress(stop: DraftStop): { tokens: string[]; fallbackToken?: string } {
  const type = (stop.stop_type || "").toUpperCase();
  const isPickup = type === "PICKUP";
  const isDelivery = type === "DELIVERY" || type === "DROP";
  const parts = [stop.street, stop.city, stop.state_or_province, stop.postal_code, stop.facility_name]
    .map((x) => (x ?? "").trim())
    .filter(Boolean);
  const tokens = [
    ...parts.slice(0, 6),
    ...(isPickup ? ["pickup", "pick up", "origin", "shipper", "ship from", "pu", "load at"] : []),
    ...(isDelivery ? ["delivery", "deliver", "drop", "consignee", "ship to", "dest", "unload"] : []),
    "address",
    "location",
  ];
  return {
    tokens,
    fallbackToken: parts[0] || (isPickup ? "pickup" : isDelivery ? "delivery" : "address"),
  };
}

export function docFocusForStopAppointment(stop: DraftStop): { tokens: string[]; fallbackToken?: string } {
  const type = (stop.stop_type || "").toUpperCase();
  const isPickup = type === "PICKUP";
  const isDelivery = type === "DELIVERY" || type === "DROP";
  const tokens = [
    (stop.appointment_date ?? "").trim(),
    (stop.appointment_time_text ?? "").trim(),
    (stop.appointment_type ?? "").trim(),
    ...(isPickup ? ["pickup", "pu appt", "pick up appt", "loading", "origin appt", "shipper appt"] : []),
    ...(isDelivery
      ? ["delivery appt", "delivery appointment", "unloading", "receiver appt", "consignee appt"]
      : []),
    "appointment",
    "appt",
    "appt.",
    "window",
    "fcfs",
    "strict",
  ].filter(Boolean);
  const fallback =
    (stop.appointment_time_text || "").trim() ||
    (stop.appointment_date || "").trim() ||
    (isPickup ? "pickup" : isDelivery ? "delivery" : "appointment");
  return { tokens, fallbackToken: fallback };
}

export function docFocusForStopReference(stop: DraftStop): { tokens: string[]; fallbackToken?: string } {
  const type = (stop.stop_type || "").toUpperCase();
  const isPickup = type === "PICKUP";
  const isDelivery = type === "DELIVERY" || type === "DROP";
  const ref = (stop.reference_number ?? "").trim();
  const tokens = [
    ref,
    ...(isPickup ? ["pickup ref", "shipper ref", "origin ref"] : []),
    ...(isDelivery ? ["delivery ref", "receiver ref", "consignee ref"] : []),
    "po",
    "p.o",
    "p/o",
    "reference",
    "ref",
    "ref #",
    "ref no",
    "order",
    "bol",
    "b.o.l",
    "pickup #",
  ].filter(Boolean);
  return { tokens, fallbackToken: ref || "reference" };
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

/** Body for PATCH (edit) or POST (create) — matches LoadWorkspacePage save shape. */
export function buildLoadPersistPayload(params: {
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
  driverId: number | null;
  truckId: number | null;
  trailerId: number | null;
  customsBrokerId: number | null;
  internalNotes: string;
  draftStops: DraftStop[];
}): LoadWritePayload {
  const sorted = selectDraftStopsForPersist(params.draftStops);
  const stopsPayload = sorted.map((s, i) => stopToPayload(s, i));
  const estW = params.estimatedWeight.trim();
  const rateN = params.rate.trim();
  const crN = params.customerRate.trim();
  const milesN = params.miles.trim();

  return {
    status: params.status as Load["status"],
    load_number: params.loadNumber.trim() || null,
    broker_id: params.brokerId,
    broker_contact_id: params.brokerContactId,
    broker_name_snapshot: params.brokerNameSnapshot.trim() || null,
    broker_contact_name_snapshot: params.brokerContactNameSnapshot.trim() || null,
    broker_contact_phone_snapshot: params.brokerContactPhoneSnapshot.trim() || null,
    broker_contact_extension_snapshot: params.brokerContactExtensionSnapshot.trim() || null,
    broker_contact_email_snapshot: params.brokerContactEmailSnapshot.trim() || null,
    broker_load_reference: params.brokerLoadReference.trim() || null,
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
    driver_id: params.driverId,
    truck_id: params.truckId,
    trailer_id: params.trailerId,
    customs_broker_id: params.customsBrokerId,
    internal_notes: params.internalNotes.trim() || null,
    stops: stopsPayload,
  };
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
    status: l.status ?? "",
    loadNumber: l.load_number || "",
    brokerId: l.broker_id ?? null,
    brokerContactId: l.broker_contact_id ?? null,
    brokerNameSnapshot: l.broker_name_snapshot ?? "",
    brokerContactNameSnapshot: l.broker_contact_name_snapshot ?? "",
    brokerContactPhoneSnapshot: l.broker_contact_phone_snapshot ?? "",
    brokerContactExtensionSnapshot: l.broker_contact_extension_snapshot ?? "",
    brokerContactEmailSnapshot: l.broker_contact_email_snapshot ?? "",
    brokerLoadReference: l.broker_load_reference ?? "",
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
    driverId: l.driver_id ?? null,
    truckId: l.truck_id ?? null,
    trailerId: l.trailer_id ?? null,
    customsBrokerId: l.customs_broker_id ?? null,
    internalNotes: l.internal_notes ?? "",
    draftStops: stopsToDraft(l.stops),
  });
  return JSON.stringify(payload);
}

/** Maps `WorkspaceDraftFields` into the existing persist payload shape (single call site for saves). */
export function buildLoadPersistPayloadFromWorkspaceFields(f: WorkspaceDraftFields): LoadWritePayload {
  return buildLoadPersistPayload({
    status: f.status,
    loadNumber: f.loadNumber,
    brokerId: f.brokerId,
    brokerContactId: f.brokerContactId,
    brokerNameSnapshot: f.brokerNameSnapshot,
    brokerContactNameSnapshot: f.brokerContactNameSnapshot,
    brokerContactPhoneSnapshot: f.brokerContactPhoneSnapshot,
    brokerContactExtensionSnapshot: f.brokerContactExtensionSnapshot,
    brokerContactEmailSnapshot: f.brokerContactEmailSnapshot,
    brokerLoadReference: f.brokerLoadReference,
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
    driverId: f.driverId,
    truckId: f.truckId,
    trailerId: f.trailerAssetId,
    customsBrokerId: f.customsBrokerId,
    internalNotes: f.internalNotes,
    draftStops: f.draftStops,
  });
}
