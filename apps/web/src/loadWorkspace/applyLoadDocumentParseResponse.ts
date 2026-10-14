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
import {
  applyParseScalarHydration,
  createEmptyParseHydrationState,
  type ParseHydrationState,
} from "@/loadWorkspace/loadParseHydrationState";
import type { DraftStop } from "@/loadWorkspace/loadWorkspaceShared";

function mapParsedStopType(raw: string | null | undefined): {
  stop_type: DraftStop["stop_type"];
  parseStopTypeEvidence: string | null;
} {
  const evidence = (raw ?? "").trim() || null;
  const t = (raw || "").toLowerCase();
  if (t === "pickup") return { stop_type: "PICKUP", parseStopTypeEvidence: null };
  if (t === "drop") return { stop_type: "DROP", parseStopTypeEvidence: null };
  if (t === "delivery") return { stop_type: "DELIVERY", parseStopTypeEvidence: null };
  return { stop_type: "UNRESOLVED", parseStopTypeEvidence: evidence ?? "unknown" };
}

/** @deprecated Use session parse hydration (Issue I18); kept for tests that need a full reset. */
export function clearParseOwnedCommercialFields(cbs: ApplyLoadDocumentParseCallbacks): void {
  cbs.setBrokerNameSnapshot("");
  cbs.setBrokerId(null);
  cbs.setBrokerContactId(null);
  cbs.setBrokerContacts([]);
  cbs.setBrokerContactNameSnapshot("");
  cbs.setBrokerContactPhoneSnapshot("");
  cbs.setBrokerContactEmailSnapshot("");
  cbs.setBrokerLoadReference("");
  cbs.setLoadReferences([]);
  cbs.setFreightMode("");
  cbs.setEquipmentType("");
  cbs.setTrailerType("");
  cbs.setTrailerSize("");
  cbs.setCommodity("");
  cbs.setEstimatedWeight("");
  cbs.setTemperatureRequirement("");
  cbs.setRate("");
  cbs.setCustomerRate("");
  cbs.setMiles("");
}

export function extractedStopsToDraft(stops: LoadDocumentParseStop[]): DraftStop[] {
  const ts = Date.now();
  return stops.map((s, i) => {
    const mapped = mapParsedStopType(s.stop_type);
    const stop_type = mapped.stop_type;
    return {
      id: 0,
      load_id: 0,
      stop_type,
      parseStopTypeEvidence: mapped.parseStopTypeEvidence,
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
  /** Current operator notes before parse apply (Issue I7 — do not overwrite). */
  existingInternalNotes?: string;
  setDraftStops: Dispatch<SetStateAction<DraftStop[]>>;
}

export interface ApplyLoadDocumentParseSummary {
  resolvedBrokerId: number | null;
  brokerContactMatched: boolean;
  mcOrDotAttempted: boolean;
  /** Issue I19 — stops needing operator classification before save. */
  unresolvedStopCount: number;
  /** Session-only parse ownership (Issue I18). */
  parseHydrationState: ParseHydrationState;
}

/**
 * Apply parse response to workspace state (broker resolution, contacts list, field snapshots, stops, internal notes).
 * Does not set parse warnings or toolbar — caller owns UX feedback.
 */
export async function applyLoadDocumentParseResponse(
  res: LoadDocumentParseResponse,
  cbs: ApplyLoadDocumentParseCallbacks,
  parseHydrationState?: ParseHydrationState,
): Promise<ApplyLoadDocumentParseSummary> {
  const hydration =
    parseHydrationState != null ? parseHydrationState : createEmptyParseHydrationState();
  const ex = res.extracted;
  let resolvedBrokerIdForSummary: number | null = null;
  let brokerContactMatchedForSummary = false;

  const nextHydration = applyParseScalarHydration(ex, cbs, hydration);

  const mcSnap = ex.broker_mc_number_snapshot?.trim() ?? "";
  const dotSnap = ex.broker_dot_number_snapshot?.trim() ?? "";
  const mcOrDotAttempted = Boolean(mcSnap || dotSnap);

  if (mcOrDotAttempted) {
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
  cbs.setLoadReferences(workspaceReferencesFromParse(ex.references));

  if (ex.customs_broker_name?.trim()) {
    const prior = (cbs.existingInternalNotes ?? "").trim();
    const cline = `Customs broker (from document): ${ex.customs_broker_name.trim()}`;
    cbs.setInternalNotes(prior ? `${prior}\n\n---\n${cline}` : cline);
  }

  const meaningfulStops = filterMeaningfulParsedStops(ex.stops ?? []);
  let unresolvedStopCount = 0;
  if (meaningfulStops.length > 0) {
    const draft = extractedStopsToDraft(meaningfulStops);
    unresolvedStopCount = draft.filter((d) => (d.stop_type || "").toUpperCase() === "UNRESOLVED").length;
    cbs.setDraftStops(draft);
  }

  return {
    resolvedBrokerId: resolvedBrokerIdForSummary,
    brokerContactMatched: brokerContactMatchedForSummary,
    mcOrDotAttempted,
    unresolvedStopCount,
    parseHydrationState: nextHydration,
  };
}
