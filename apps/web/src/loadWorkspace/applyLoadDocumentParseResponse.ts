/**
 * Shared hydration from POST /loads/parse-document (and Lab parse_response) into workspace draft state.
 * Behavior must stay aligned with LoadWorkspacePage PDF apply — changes belong here + one call site test.
 */
import type { Dispatch, SetStateAction } from "react";
import type { BrokerContact, LoadDocumentParseReference, LoadDocumentParseResponse, LoadDocumentParseStop } from "@/api";
import { resolveBrokerIdentity, listBrokerContacts } from "@/api";
import { matchBrokerContactFromParsed } from "@/utils/matchBrokerFromSnapshot";
import { filterMeaningfulParsedStops } from "@/loadWorkspace/loadParseStops";
import {
  shouldPreserveWorkspaceLoadReferences,
  workspaceReferencesFromParse,
} from "@/loadWorkspace/loadOperationalReferences";
import {
  applyContactDraftValueToLoadPersist,
  applyParseScalarHydration,
  applyScalarDraftValueToLoadPersist,
  brokerContactIdInContactList,
  createEmptyParseHydrationState,
  effectiveParseCustomerRateString,
  type ParseContactFieldKey,
  type ParseHydrationState,
} from "@/loadWorkspace/loadParseHydrationState";
import {
  draftJsonDefinesField,
  type DraftStop,
  type LoadPersistParams,
  type WorkspaceDraftFields,
} from "@/loadWorkspace/loadWorkspaceShared";
import { initialManualCreateStops } from "@/loadWorkspace/loadWorkspaceShared";
import { hasUsefulStopIdentity } from "@/loadWorkspace/loadParseStops";

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
  resolvedBrokerContactId: number | null;
  brokerContactMatched: boolean;
  mcOrDotAttempted: boolean;
  /** Issue I19 — stops needing operator classification before save. */
  unresolvedStopCount: number;
  /** Session-only parse ownership (Issue I18). */
  parseHydrationState: ParseHydrationState;
  /** Operator-visible notes when parse hydration kept manual edits (e.g. stops). */
  hydrationReviewNotes: string[];
}

function trimmedOrEmpty(v: string | null | undefined): string {
  return (v ?? "").trim();
}

function workspaceFieldEmpty(value: string | null | undefined): boolean {
  return !trimmedOrEmpty(value);
}

/** Reopen draft: merge parse into form only where persisted draft_json left a field blank. */
export function applyEmptyWorkspaceFieldsFromParseResponse(
  fields: WorkspaceDraftFields,
  res: LoadDocumentParseResponse,
  cbs: ApplyLoadDocumentParseCallbacks,
  draftJson?: Record<string, unknown>,
): void {
  const ex = res.extracted;
  const fillString = (
    current: string,
    parsed: string | null | undefined,
    set: (v: string) => void,
    draftKeys: string[],
  ) => {
    if (draftJsonDefinesField(draftJson, draftKeys)) return;
    if (!workspaceFieldEmpty(current)) return;
    const next = trimmedOrEmpty(parsed);
    if (next) set(next);
  };

  fillString(
    fields.brokerNameSnapshot,
    ex.broker_name_snapshot,
    cbs.setBrokerNameSnapshot,
    ["brokerNameSnapshot", "broker_name_snapshot"],
  );
  fillString(
    fields.brokerLoadReference,
    ex.broker_load_reference,
    cbs.setBrokerLoadReference,
    ["brokerLoadReference", "broker_load_reference"],
  );
  fillString(
    fields.brokerContactNameSnapshot,
    ex.broker_contact_name_snapshot,
    cbs.setBrokerContactNameSnapshot,
    ["brokerContactNameSnapshot", "broker_contact_name_snapshot"],
  );
  fillString(
    fields.brokerContactPhoneSnapshot,
    ex.broker_contact_phone_snapshot,
    cbs.setBrokerContactPhoneSnapshot,
    ["brokerContactPhoneSnapshot", "broker_contact_phone_snapshot"],
  );
  fillString(
    fields.brokerContactEmailSnapshot,
    ex.broker_contact_email_snapshot,
    cbs.setBrokerContactEmailSnapshot,
    ["brokerContactEmailSnapshot", "broker_contact_email_snapshot"],
  );
  fillString(fields.freightMode, ex.mode, cbs.setFreightMode, ["freightMode", "mode"]);
  fillString(fields.equipmentType, ex.equipment_type, cbs.setEquipmentType, ["equipmentType", "equipment_type"]);
  fillString(fields.trailerType, ex.trailer_type, cbs.setTrailerType, ["trailerType", "trailer_type"]);
  fillString(fields.trailerSize, ex.trailer_size, cbs.setTrailerSize, ["trailerSize", "trailer_size"]);
  fillString(fields.commodity, ex.commodity, cbs.setCommodity, ["commodity"]);
  fillString(
    fields.temperatureRequirement,
    ex.temperature_requirement,
    cbs.setTemperatureRequirement,
    ["temperatureRequirement", "temperature_requirement"],
  );

  if (
    !draftJsonDefinesField(draftJson, ["estimatedWeight", "estimated_weight"]) &&
    workspaceFieldEmpty(fields.estimatedWeight) &&
    ex.estimated_weight != null
  ) {
    cbs.setEstimatedWeight(String(ex.estimated_weight));
  }
  if (
    !draftJsonDefinesField(draftJson, ["rate"]) &&
    workspaceFieldEmpty(fields.rate) &&
    ex.rate != null
  ) {
    cbs.setRate(String(ex.rate));
  }
  if (
    !draftJsonDefinesField(draftJson, ["customerRate", "customer_rate"]) &&
    workspaceFieldEmpty(fields.customerRate) &&
    effectiveParseCustomerRateString(ex) != null
  ) {
    cbs.setCustomerRate(ex.customer_rate != null ? String(ex.customer_rate) : "");
  }
  if (
    !draftJsonDefinesField(draftJson, ["miles"]) &&
    workspaceFieldEmpty(fields.miles) &&
    ex.miles != null
  ) {
    cbs.setMiles(String(Math.round(ex.miles)));
  }

  if (
    !draftJsonDefinesField(draftJson, ["loadReferences", "references"]) &&
    (fields.loadReferences?.length ?? 0) === 0
  ) {
    const refs = workspaceReferencesFromParse(ex.references);
    if (refs.length > 0) cbs.setLoadReferences(refs);
  }

  const hasStopIdentity = fields.draftStops.some((s) => hasUsefulStopIdentity(s));
  if (!hasStopIdentity) {
    const meaningfulStops = filterMeaningfulParsedStops(ex.stops ?? []);
    if (meaningfulStops.length > 0) {
      cbs.setDraftStops(extractedStopsToDraft(meaningfulStops));
    }
  }

  if (workspaceFieldEmpty(fields.internalNotes) && ex.customs_broker_name?.trim()) {
    cbs.setInternalNotes(`Customs broker (from document): ${ex.customs_broker_name.trim()}`);
  }
}

/** Merge parse extract with operator manual edits captured at parse start (not async React state). */
export function buildLoadPersistParamsAfterParseApply(
  workspaceAtParseStart: WorkspaceDraftFields,
  res: LoadDocumentParseResponse,
  summary: ApplyLoadDocumentParseSummary,
  seed: {
    loadNumber?: string;
    hazmat?: LoadPersistParams["hazmat"];
    palletCaseCount?: string;
    customsBrokerId?: number | null;
    existingInternalNotes?: string;
    driverId?: number | null;
    truckId?: number | null;
    trailerAssetId?: number | null;
  } = {},
): LoadPersistParams {
  const params = buildLoadPersistParamsFromParseResponse(res, summary, seed);
  const hydration = summary.parseHydrationState;
  for (const key of hydration.manualOverrideKeys) {
    applyScalarDraftValueToLoadPersist(params, key, workspaceAtParseStart);
  }
  for (const key of hydration.manualContactFieldKeys) {
    applyContactDraftValueToLoadPersist(params, key, workspaceAtParseStart);
  }
  if (hydration.stopsRouteManuallyEdited) {
    params.draftStops = workspaceAtParseStart.draftStops;
  }
  if (
    hydration.brokerIdentityLocked ||
    hydration.manualOverrideKeys.has("brokerNameSnapshot")
  ) {
    params.brokerId = workspaceAtParseStart.brokerId;
    params.brokerNameSnapshot = workspaceAtParseStart.brokerNameSnapshot;
  }
  /** Authoritative contact id after apply (null when cleared or unmatched). */
  params.brokerContactId = summary.resolvedBrokerContactId;
  const guardRefs = workspaceAtParseStart.loadReferences ?? [];
  const parsedRefs = workspaceReferencesFromParse(res.extracted.references);
  if (
    shouldPreserveWorkspaceLoadReferences(
      guardRefs,
      res.extracted.references,
      hydration.loadReferencesManuallyEdited,
    )
  ) {
    params.loadReferences = guardRefs;
  }
  return params;
}

export type PersistWorkspaceDraftAfterParseInput = {
  draftId: string;
  draftVersion: number;
  res: LoadDocumentParseResponse;
  summary: ApplyLoadDocumentParseSummary;
  /** Workspace commercial snapshot taken synchronously before parse hydration runs. */
  workspaceAtParseStart: WorkspaceDraftFields;
  status: string;
  seed: {
    loadNumber: string;
    hazmat: LoadPersistParams["hazmat"];
    palletCaseCount: string;
    customsBrokerId: number | null;
    existingInternalNotes: string;
    driverId?: number | null;
    truckId?: number | null;
    trailerAssetId?: number | null;
  };
  updateDraft: (
    draftId: string,
    body: { expected_concurrency_version: number; draft_json: Record<string, unknown> },
  ) => Promise<{ concurrency_version: number; draft_json?: Record<string, unknown> }>;
  buildDraftJson: (params: LoadPersistParams & { status: string }) => Record<string, unknown>;
};

/** Persist draft_json after parse; throws on failure (no soft fallback). */
export async function persistWorkspaceDraftAfterParse(
  input: PersistWorkspaceDraftAfterParseInput,
): Promise<{ concurrency_version: number; draft_json?: Record<string, unknown> }> {
  const persistParams = buildLoadPersistParamsAfterParseApply(
    input.workspaceAtParseStart,
    input.res,
    input.summary,
    {
      loadNumber: input.seed.loadNumber,
      hazmat: input.seed.hazmat,
      palletCaseCount: input.seed.palletCaseCount,
      customsBrokerId: input.seed.customsBrokerId,
      existingInternalNotes: input.seed.existingInternalNotes,
      driverId: input.seed.driverId,
      truckId: input.seed.truckId,
      trailerAssetId: input.seed.trailerAssetId,
    },
  );
  try {
    const draftJson = input.buildDraftJson({ ...persistParams, status: input.status });
    const saved = await input.updateDraft(input.draftId, {
      expected_concurrency_version: input.draftVersion,
      draft_json: draftJson,
    });

    // The accepted parser output and editable draft are separate on purpose:
    // never silently promote unreviewed stops. Protect the explicit post-parse
    // draft save from dropping source stop rows during the server round trip.
    // This is NOT a completeness gate on manual / workspace promotion.
    if (filterMeaningfulParsedStops(input.res.extracted.stops ?? []).length > 0) {
      const requested = draftJson.draftStops;
      const persisted = saved.draft_json?.draftStops;
      const identityFields = [
        "stop_type", "sequence", "facility_name", "street", "city",
        "state_or_province", "postal_code", "country", "reference_number",
        "appointment_type", "appointment_date", "appointment_time_text",
        "notes", "commodity_notes",
      ] as const;
      const textAt = (row: unknown, field: string): string =>
        row && typeof row === "object"
          ? String((row as Record<string, unknown>)[field] ?? "").trim()
          : "";
      const missingOrChanged =
        !Array.isArray(requested) ||
        !Array.isArray(persisted) ||
        requested.length !== persisted.length ||
        requested.some((stop, index) =>
          identityFields.some((field) => textAt(stop, field) !== textAt(persisted[index], field)),
        );
      if (missingOrChanged) {
        throw new Error(
          "Parsed pickup/delivery stops were not preserved in the saved draft. Reopen the draft and verify stops before creating a load.",
        );
      }
    }
    return saved;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Could not save draft after parse";
    throw new Error(msg);
  }
}

/** Build persist payload from parse output (for draft_json after parse — no React state round-trip). */
export function buildLoadPersistParamsFromParseResponse(
  res: LoadDocumentParseResponse,
  summary: ApplyLoadDocumentParseSummary,
  seed: {
    loadNumber?: string;
    hazmat?: LoadPersistParams["hazmat"];
    palletCaseCount?: string;
    customsBrokerId?: number | null;
    existingInternalNotes?: string;
    driverId?: number | null;
    truckId?: number | null;
    trailerAssetId?: number | null;
  } = {},
): LoadPersistParams {
  const ex = res.extracted;
  const meaningfulStops = filterMeaningfulParsedStops(ex.stops ?? []);
  const draftStops =
    meaningfulStops.length > 0 ? extractedStopsToDraft(meaningfulStops) : initialManualCreateStops();

  let internalNotes = (seed.existingInternalNotes ?? "").trim();
  if (ex.customs_broker_name?.trim()) {
    const cline = `Customs broker (from document): ${ex.customs_broker_name.trim()}`;
    internalNotes = internalNotes ? `${internalNotes}\n\n---\n${cline}` : cline;
  }

  return {
    loadNumber: seed.loadNumber ?? "",
    brokerId: summary.resolvedBrokerId,
    brokerContactId: summary.resolvedBrokerContactId,
    brokerNameSnapshot: trimmedOrEmpty(ex.broker_name_snapshot),
    brokerContactNameSnapshot: trimmedOrEmpty(ex.broker_contact_name_snapshot),
    brokerContactPhoneSnapshot: trimmedOrEmpty(ex.broker_contact_phone_snapshot),
    brokerContactExtensionSnapshot: "",
    brokerContactEmailSnapshot: trimmedOrEmpty(ex.broker_contact_email_snapshot),
    brokerLoadReference: trimmedOrEmpty(ex.broker_load_reference),
    loadReferences: workspaceReferencesFromParse(ex.references),
    mode: trimmedOrEmpty(ex.mode),
    equipmentType: trimmedOrEmpty(ex.equipment_type),
    trailerType: trimmedOrEmpty(ex.trailer_type),
    trailerSize: trimmedOrEmpty(ex.trailer_size),
    commodity: trimmedOrEmpty(ex.commodity),
    estimatedWeight: ex.estimated_weight != null ? String(ex.estimated_weight) : "",
    hazmat: seed.hazmat ?? "unset",
    temperatureRequirement: trimmedOrEmpty(ex.temperature_requirement),
    palletCaseCount: seed.palletCaseCount ?? "",
    rate: ex.rate != null ? String(ex.rate) : "",
    customerRate: ex.customer_rate != null ? String(ex.customer_rate) : "",
    miles: ex.miles != null ? String(Math.round(ex.miles)) : "",
    customsBrokerId: seed.customsBrokerId ?? null,
    internalNotes,
    draftStops,
    driverId: seed.driverId ?? null,
    truckId: seed.truckId ?? null,
    trailerAssetId: seed.trailerAssetId ?? null,
  };
}

/**
 * Apply parse response to workspace state (broker resolution, contacts list, field snapshots, stops, internal notes).
 * Does not set parse warnings or toolbar — caller owns UX feedback.
 */
export type ParseIdentityGuard = Pick<
  WorkspaceDraftFields,
  "brokerId" | "brokerNameSnapshot" | "brokerContactId" | "loadReferences" | "brokerLoadReference"
>;

export async function applyLoadDocumentParseResponse(
  res: LoadDocumentParseResponse,
  cbs: ApplyLoadDocumentParseCallbacks,
  parseHydrationState?: ParseHydrationState,
  identityGuard?: ParseIdentityGuard,
): Promise<ApplyLoadDocumentParseSummary> {
  const hydration =
    parseHydrationState != null ? parseHydrationState : createEmptyParseHydrationState();
  const ex = res.extracted;
  let resolvedBrokerIdForSummary: number | null = identityGuard?.brokerId ?? null;
  let resolvedBrokerContactIdForSummary: number | null = identityGuard?.brokerContactId ?? null;
  let brokerContactMatchedForSummary = false;

  const nextHydration = applyParseScalarHydration(ex, cbs, hydration);
  const hydrationReviewNotes: string[] = [];
  const brokerIdentityProtected =
    nextHydration.brokerIdentityLocked || nextHydration.manualOverrideKeys.has("brokerNameSnapshot");

  const contactSelectionProtected = (): boolean =>
    nextHydration.brokerContactIdManuallySelected ||
    nextHydration.manualContactFieldKeys.size > 0;

  const clearBrokerContactSelection = (reviewNote?: string) => {
    cbs.setBrokerContactId(null);
    nextHydration.brokerContactIdManuallySelected = false;
    resolvedBrokerContactIdForSummary = null;
    brokerContactMatchedForSummary = false;
    if (reviewNote) hydrationReviewNotes.push(reviewNote);
  };

  const applyContact = (
    key: ParseContactFieldKey,
    parsed: string | null | undefined,
    set: (v: string) => void,
  ) => {
    if (nextHydration.manualContactFieldKeys.has(key)) return;
    const v = trimmedOrEmpty(parsed);
    if (!v) return;
    set(v);
    nextHydration.lastAppliedContactValues.set(key, v);
  };

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

    const priorBrokerId = identityGuard?.brokerId ?? null;
    const priorContactId = identityGuard?.brokerContactId ?? null;
    const parserBrokerDiffers =
      resolvedBrokerId != null && priorBrokerId != null && resolvedBrokerId !== priorBrokerId;

    if (brokerIdentityProtected && identityGuard) {
      resolvedBrokerIdForSummary = identityGuard.brokerId;
      const parsedName = trimmedOrEmpty(ex.broker_name_snapshot);
      const keptName = trimmedOrEmpty(identityGuard.brokerNameSnapshot);
      if (parsedName && keptName && parsedName !== keptName) {
        hydrationReviewNotes.push(
          `Parser extracted broker "${parsedName}"; your broker "${keptName}" was kept. Review before save.`,
        );
      } else if (parserBrokerDiffers) {
        hydrationReviewNotes.push(
          "Parser MC/DOT matches a different broker record; your broker selection was kept. Review before save.",
        );
      }
      if (identityGuard.brokerId != null) {
        try {
          const paged = await listBrokerContacts(identityGuard.brokerId, {
            page: 1,
            size: 200,
            include_archived: false,
          });
          const items = paged.items || [];
          cbs.setBrokerContacts(items);
          if (
            contactSelectionProtected() &&
            priorContactId != null &&
            brokerContactIdInContactList(priorContactId, items)
          ) {
            resolvedBrokerContactIdForSummary = priorContactId;
            cbs.setBrokerContactId(priorContactId);
          } else if (priorContactId != null) {
            clearBrokerContactSelection(
              "The selected broker contact does not belong to the chosen broker and was cleared. Pick a contact for this broker.",
            );
          }
        } catch {
          cbs.setBrokerContacts([]);
          if (priorContactId != null) {
            clearBrokerContactSelection(
              "Could not verify broker contact membership; the contact was not kept. Review before save.",
            );
          }
        }
      }
    } else {
      resolvedBrokerIdForSummary = resolvedBrokerId;
      cbs.setBrokerId(resolvedBrokerId);

      const brokerChanged =
        resolvedBrokerId != null && priorBrokerId != null && resolvedBrokerId !== priorBrokerId;
      if (brokerChanged && priorContactId != null) {
        clearBrokerContactSelection(
          "Parser identified a different broker; the previous broker contact was cleared. Select a contact for the new broker.",
        );
      } else if (!contactSelectionProtected()) {
        clearBrokerContactSelection();
      }

      if (resolvedBrokerId != null) {
        try {
          const paged = await listBrokerContacts(resolvedBrokerId, {
            page: 1,
            size: 200,
            include_archived: false,
          });
          const items = paged.items || [];
          cbs.setBrokerContacts(items);
          if (
            contactSelectionProtected() &&
            !brokerChanged &&
            priorContactId != null &&
            priorBrokerId === resolvedBrokerId &&
            brokerContactIdInContactList(priorContactId, items)
          ) {
            resolvedBrokerContactIdForSummary = priorContactId;
            cbs.setBrokerContactId(priorContactId);
          } else if (
            contactSelectionProtected() &&
            priorContactId != null &&
            (brokerChanged || !brokerContactIdInContactList(priorContactId, items))
          ) {
            clearBrokerContactSelection(
              "The selected broker contact does not belong to the identified broker and was cleared.",
            );
          } else if (!contactSelectionProtected()) {
            const matchedContact = matchBrokerContactFromParsed(items, {
              name: ex.broker_contact_name_snapshot,
              email: ex.broker_contact_email_snapshot,
              phone: ex.broker_contact_phone_snapshot,
            });
            if (matchedContact) {
              brokerContactMatchedForSummary = true;
              resolvedBrokerContactIdForSummary = matchedContact.id;
              cbs.setBrokerContactId(matchedContact.id);
            } else {
              resolvedBrokerContactIdForSummary = null;
            }
          }
        } catch {
          cbs.setBrokerContacts([]);
          if (priorContactId != null) {
            clearBrokerContactSelection(
              "Could not verify broker contact membership; the contact was not kept. Review before save.",
            );
          } else {
            resolvedBrokerContactIdForSummary = null;
          }
        }
      } else if (!contactSelectionProtected()) {
        cbs.setBrokerContacts([]);
        resolvedBrokerContactIdForSummary = null;
      }
    }
  }

  applyContact("brokerContactName", ex.broker_contact_name_snapshot, cbs.setBrokerContactNameSnapshot);
  applyContact("brokerContactPhone", ex.broker_contact_phone_snapshot, cbs.setBrokerContactPhoneSnapshot);
  applyContact("brokerContactEmail", ex.broker_contact_email_snapshot, cbs.setBrokerContactEmailSnapshot);
  const parsedRefs = workspaceReferencesFromParse(ex.references);
  const guardRefs = identityGuard?.loadReferences ?? [];
  const preserveRefs = shouldPreserveWorkspaceLoadReferences(
    guardRefs,
    ex.references,
    nextHydration.loadReferencesManuallyEdited,
  );
  if (preserveRefs) {
    if (parsedRefs.length > 0) {
      hydrationReviewNotes.push(
        "Parser returned updated load references; your reviewed references were kept. Compare with the PDF before save.",
      );
    }
  } else {
    cbs.setLoadReferences(parsedRefs);
  }

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
    if (nextHydration.stopsRouteManuallyEdited) {
      hydrationReviewNotes.push(
        "Parser returned updated stops; your edited route was kept. Review stops against the PDF before save.",
      );
    } else {
      cbs.setDraftStops(draft);
      nextHydration.stopsRouteManuallyEdited = false;
    }
  }

  return {
    resolvedBrokerId: resolvedBrokerIdForSummary,
    resolvedBrokerContactId: resolvedBrokerContactIdForSummary,
    brokerContactMatched: brokerContactMatchedForSummary,
    mcOrDotAttempted,
    unresolvedStopCount,
    parseHydrationState: nextHydration,
    hydrationReviewNotes,
  };
}
