/**
 * Shared hydration from POST /loads/parse-document (and Lab parse_response) into workspace draft state.
 * Behavior must stay aligned with LoadWorkspacePage PDF apply — changes belong here + one call site test.
 */
import type { Dispatch, SetStateAction } from "react";
import type { BrokerContact, LoadDocumentParseReference, LoadDocumentParseResponse, LoadDocumentParseStop } from "@/api";
import { resolveBrokerIdentity, listBrokerContacts } from "@/api";
import { matchBrokerContactFromParsed } from "@/utils/matchBrokerFromSnapshot";
import { filterMeaningfulParsedStops } from "@/loadWorkspace/loadParseStops";
import { workspaceReferencesFromParse } from "@/loadWorkspace/loadOperationalReferences";
import type { DraftStop } from "@/loadWorkspace/loadWorkspaceShared";

export function extractedStopsToDraft(stops: LoadDocumentParseStop[]): DraftStop[] {
  const ts = Date.now();
  return stops.map((s, i) => {
    const t = (s.stop_type || "").toLowerCase();
    let stop_type: DraftStop["stop_type"] = "DELIVERY";
    if (t === "pickup") stop_type = "PICKUP";
    else if (t === "drop") stop_type = "DROP";
    else if (t === "delivery") stop_type = "DELIVERY";
    return {
      id: 0,
      load_id: 0,
      stop_type,
      sequence: s.sequence ?? i,
      facility_name: s.facility_name ?? null,
      street: s.street ?? null,
      city: s.city ?? null,
      state_or_province: s.state_or_province ?? null,
      postal_code: s.postal_code ?? null,
      country: s.country ?? null,
      reference_number: s.reference_number ?? null,
      appointment_type: s.appointment_type ?? null,
      appointment_date: s.appointment_date ?? null,
      appointment_time_text: s.appointment_time_text ?? null,
      scheduled_at: null,
      notes: s.notes ?? null,
      commodity_notes: null,
      created_at: null,
      updated_at: null,
      _key: `pdf-${ts}-${i}-${Math.random().toString(36).slice(2, 8)}`,
    };
  });
}

/** Setters for every field touched by PDF parse hydration (workspace + Lab). */
export interface ApplyLoadDocumentParseCallbacks {
  setBrokerNameSnapshot: (v: string) => void;
  setBrokerId: (v: number | null) => void;
  setBrokerContactId: (v: number | null) => void;
  setBrokerContacts: (v: BrokerContact[]) => void;
  setBrokerContactNameSnapshot: (v: string) => void;
  setBrokerContactPhoneSnapshot: (v: string) => void;
  setBrokerContactEmailSnapshot: (v: string) => void;
  setBrokerLoadReference: (v: string) => void;
  setLoadReferences: (v: LoadDocumentParseReference[]) => void;
  setFreightMode: (v: string) => void;
  setEquipmentType: (v: string) => void;
  setTrailerType: (v: string) => void;
  setTrailerSize: (v: string) => void;
  setCommodity: (v: string) => void;
  setEstimatedWeight: (v: string) => void;
  setTemperatureRequirement: (v: string) => void;
  setRate: (v: string) => void;
  setCustomerRate: (v: string) => void;
  setMiles: (v: string) => void;
  setInternalNotes: (v: string) => void;
  setDraftStops: Dispatch<SetStateAction<DraftStop[]>>;
}

export interface ApplyLoadDocumentParseSummary {
  resolvedBrokerId: number | null;
  brokerContactMatched: boolean;
  mcOrDotAttempted: boolean;
}

/**
 * Apply parse response to workspace state (broker resolution, contacts list, field snapshots, stops, internal notes).
 * Does not set parse warnings or toolbar — caller owns UX feedback.
 */
export async function applyLoadDocumentParseResponse(
  res: LoadDocumentParseResponse,
  cbs: ApplyLoadDocumentParseCallbacks,
): Promise<ApplyLoadDocumentParseSummary> {
  const ex = res.extracted;
  let resolvedBrokerIdForSummary: number | null = null;
  let brokerContactMatchedForSummary = false;

  const brokerNameSnap = ex.broker_name_snapshot?.trim() ?? "";
  if (brokerNameSnap) {
    cbs.setBrokerNameSnapshot(brokerNameSnap);
  }

  const mcSnap = ex.broker_mc_number_snapshot?.trim() ?? "";
  const dotSnap = ex.broker_dot_number_snapshot?.trim() ?? "";
  const mcOrDotAttempted = Boolean(mcSnap || dotSnap);

  if (mcSnap || dotSnap) {
    let resolvedBrokerId: number | null = null;
    try {
      const resolved = await resolveBrokerIdentity({
        mc_number: mcSnap || undefined,
        dot_number: dotSnap || undefined,
      });
      resolvedBrokerId = resolved.broker_id ?? null;
    } catch {
      resolvedBrokerId = null;
    }
    resolvedBrokerIdForSummary = resolvedBrokerId;
    cbs.setBrokerId(resolvedBrokerId);
    cbs.setBrokerContactId(null);
    if (resolvedBrokerId != null) {
      try {
        const paged = await listBrokerContacts(resolvedBrokerId, {
          page: 1,
          size: 200,
          include_archived: false,
        });
        const items = paged.items || [];
        cbs.setBrokerContacts(items);
        const matchedContact = matchBrokerContactFromParsed(items, {
          name: ex.broker_contact_name_snapshot,
          email: ex.broker_contact_email_snapshot,
          phone: ex.broker_contact_phone_snapshot,
        });
        if (matchedContact) {
          brokerContactMatchedForSummary = true;
          cbs.setBrokerContactId(matchedContact.id);
        }
      } catch {
        cbs.setBrokerContacts([]);
      }
    } else {
      cbs.setBrokerContacts([]);
    }
  }

  if (ex.broker_contact_name_snapshot?.trim()) {
    cbs.setBrokerContactNameSnapshot(ex.broker_contact_name_snapshot.trim());
  }
  if (ex.broker_contact_phone_snapshot?.trim()) {
    cbs.setBrokerContactPhoneSnapshot(ex.broker_contact_phone_snapshot.trim());
  }
  if (ex.broker_contact_email_snapshot?.trim()) {
    cbs.setBrokerContactEmailSnapshot(ex.broker_contact_email_snapshot.trim());
  }
  if (ex.broker_load_reference?.trim()) cbs.setBrokerLoadReference(ex.broker_load_reference.trim());
  cbs.setLoadReferences(workspaceReferencesFromParse(ex.references));
  if (ex.mode?.trim()) cbs.setFreightMode(ex.mode.trim());
  if (ex.equipment_type?.trim()) cbs.setEquipmentType(ex.equipment_type.trim());
  if (ex.trailer_type?.trim()) cbs.setTrailerType(ex.trailer_type.trim());
  if (ex.trailer_size?.trim()) cbs.setTrailerSize(ex.trailer_size.trim());
  if (ex.commodity?.trim()) cbs.setCommodity(ex.commodity.trim());
  if (ex.estimated_weight != null) cbs.setEstimatedWeight(String(ex.estimated_weight));
  if (ex.temperature_requirement?.trim()) {
    cbs.setTemperatureRequirement(ex.temperature_requirement.trim());
  }
  if (ex.rate != null) cbs.setRate(String(ex.rate));
  if (ex.customer_rate != null) cbs.setCustomerRate(String(ex.customer_rate));
  if (ex.miles != null) cbs.setMiles(String(Math.round(ex.miles)));

  let notesBody = res.raw_text?.trim() || "";
  if (ex.customs_broker_name?.trim()) {
    const cline = `Customs broker (from document): ${ex.customs_broker_name.trim()}`;
    notesBody = notesBody ? `${notesBody}\n\n---\n${cline}` : cline;
  }
  cbs.setInternalNotes(notesBody);

  const meaningfulStops = filterMeaningfulParsedStops(ex.stops ?? []);
  if (meaningfulStops.length > 0) {
    cbs.setDraftStops(extractedStopsToDraft(meaningfulStops));
  }

  return {
    resolvedBrokerId: resolvedBrokerIdForSummary,
    brokerContactMatched: brokerContactMatchedForSummary,
    mcOrDotAttempted,
  };
}
