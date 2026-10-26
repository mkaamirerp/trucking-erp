import { describe, expect, it, vi } from "vitest";
import type { LoadDocumentParseResponse } from "@/api";
import { listBrokerContacts, resolveBrokerIdentity } from "@/api";
import {
  applyLoadDocumentParseResponse,
  buildLoadPersistParamsAfterParseApply,
  persistWorkspaceDraftAfterParse,
} from "./applyLoadDocumentParseResponse";
import type { ApplyLoadDocumentParseCallbacks } from "./applyLoadDocumentParseResponse";
import { hydrateLoadWorkspaceFromParseResponse } from "./loadParseHydration";
import {
  applyParseScalarHydration,
  createEmptyParseHydrationState,
  hydrationStateFromDraftAndParse,
  inferParseContactConfidenceManualKeys,
  markBrokerIdentityLocked,
  markOperatorEditedParseScalar,
  registerManualParseFieldEdit,
} from "./loadParseHydrationState";
import {
  buildWorkspaceDraftJson,
  initialWorkspaceFieldsManual,
  parseManualOverrideKeysFromDraftJson,
  workspaceFieldsFromDraftJson,
  workspaceFieldsFromLoadPersistParams,
} from "./loadWorkspaceShared";

vi.mock("@/api", () => ({
  resolveBrokerIdentity: vi.fn(),
  listBrokerContacts: vi.fn(),
}));

function emptyRes(
  extracted: Record<string, unknown> = {},
  warnings: string[] = [],
): LoadDocumentParseResponse {
  return {
    document: { filename: "t.pdf" },
    extracted: { references: [], stops: [], ...extracted },
    raw_text: "body",
    warnings,
    field_confidence: {},
  };
}

function mkCbs(state: {
  rate: string;
  customerRate: string;
  brokerName: string;
  brokerId: number | null;
  brokerLoadReference: string;
  loadReferences: { kind: string; value: string; label?: string }[];
  brokerContactName: string;
  draftStops: unknown[];
}) {
  return {
    setBrokerNameSnapshot: vi.fn((v: string) => {
      state.brokerName = v;
    }),
    setBrokerId: vi.fn((v: number | null) => {
      state.brokerId = v;
    }),
    setBrokerContactId: vi.fn(),
    setBrokerContacts: vi.fn(),
    setBrokerContactNameSnapshot: vi.fn((v: string) => {
      state.brokerContactName = v;
    }),
    setBrokerContactPhoneSnapshot: vi.fn(),
    setBrokerContactEmailSnapshot: vi.fn(),
    setBrokerLoadReference: vi.fn((v: string) => {
      state.brokerLoadReference = v;
    }),
    setLoadReferences: vi.fn((v) => {
      state.loadReferences = v;
    }),
    setFreightMode: vi.fn(),
    setEquipmentType: vi.fn(),
    setTrailerType: vi.fn(),
    setTrailerSize: vi.fn(),
    setCommodity: vi.fn(),
    setEstimatedWeight: vi.fn(),
    setTemperatureRequirement: vi.fn(),
    setRate: vi.fn((v: string) => {
      state.rate = v;
    }),
    setCustomerRate: vi.fn((v: string) => {
      state.customerRate = v;
    }),
    setMiles: vi.fn(),
    setInternalNotes: vi.fn(),
    setDraftStops: vi.fn((v) => {
      state.draftStops = typeof v === "function" ? v(state.draftStops) : v;
    }),
  } satisfies ApplyLoadDocumentParseCallbacks;
}

const parseA = {
  broker_name_snapshot: "Broker A",
  broker_mc_number_snapshot: "111",
  broker_load_reference: "100",
  references: [{ kind: "po_number", value: "555", label: "PO #" }],
  rate: 1000,
};

describe("parse → manual edit → re-parse → persist", () => {
  it("keeps manually corrected rate in draft_json (not new AI extract)", async () => {
    const live = {
      rate: "",
      customerRate: "",
      brokerName: "",
      brokerId: null,
      brokerLoadReference: "",
      loadReferences: [] as { kind: string; value: string }[],
      brokerContactName: "",
      draftStops: [] as unknown[],
    };
    const cbs = mkCbs(live);
    let hydration = createEmptyParseHydrationState();

    hydration = applyParseScalarHydration({ rate: 1000 } as never, cbs, hydration);
    expect(live.rate).toBe("1000");

    registerManualParseFieldEdit(hydration, "rate", "1500");
    live.rate = "1500";
    const workspaceAtReparse = { ...initialWorkspaceFieldsManual(), rate: "1500" };

    hydration = applyParseScalarHydration({ rate: 900 } as never, cbs, hydration);
    expect(live.rate).toBe("1500");

    const res = emptyRes({ rate: 900 });
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: hydration,
      hydrationReviewNotes: [],
    };
    const params = buildLoadPersistParamsAfterParseApply(workspaceAtReparse, res, summary, {
      driverId: 42,
      truckId: 7,
      trailerAssetId: 3,
    });
    expect(params.rate).toBe("1500");
    expect(params.driverId).toBe(42);

    const updateDraft = vi.fn().mockImplementation(async (_id: string, body: { draft_json: Record<string, unknown> }) => ({
      concurrency_version: 2,
      draft_json: body.draft_json,
    }));
    const saved = await persistWorkspaceDraftAfterParse({
      draftId: "draft-x",
      draftVersion: 1,
      res,
      summary,
      workspaceAtParseStart: workspaceAtReparse,
      status: "draft",
      seed: { driverId: 42, truckId: 7, trailerAssetId: 3 },
      updateDraft,
      buildDraftJson: buildWorkspaceDraftJson,
    });
    expect(saved.draft_json?.rate).toBe("1500");
    expect(saved.draft_json?.driverId).toBe(42);

    const reopened = workspaceFieldsFromDraftJson(saved.draft_json ?? {});
    expect(reopened.rate).toBe("1500");
    const accepted = emptyRes({ rate: 900 });
    const provenance = hydrationStateFromDraftAndParse(reopened, accepted.extracted);
    expect(provenance.manualOverrideKeys.has("rate")).toBe(true);
    expect(inferParseContactConfidenceManualKeys(reopened, accepted.extracted).size).toBe(0);
  });

  it("customer rate: parse default, manual edit, save, reopen, reparse with new RC rate", async () => {
    const live = {
      rate: "",
      customerRate: "",
      brokerName: "",
      brokerId: null,
      brokerLoadReference: "",
      loadReferences: [] as { kind: string; value: string }[],
      brokerContactName: "",
      draftStops: [] as unknown[],
    };
    const cbs = mkCbs(live);
    let hydration = createEmptyParseHydrationState();

    hydration = applyParseScalarHydration({ rate: 1000 } as never, cbs, hydration);
    expect(live.rate).toBe("1000");
    expect(live.customerRate).toBe("");

    hydration = applyParseScalarHydration({ rate: 1100 } as never, cbs, hydration);
    expect(live.rate).toBe("1100");
    expect(hydration.lastAppliedValues.get("customerRate")).toBe("1100");

    markOperatorEditedParseScalar(hydration, "customerRate");
    live.customerRate = "1350";
    const workspaceAtReparse = {
      ...initialWorkspaceFieldsManual(),
      rate: "1100",
      customerRate: "1350",
    };

    hydration = applyParseScalarHydration({ rate: 900 } as never, cbs, hydration);
    expect(live.customerRate).toBe("1350");
    expect(live.rate).toBe("900");

    const res = emptyRes({ rate: 900 });
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: hydration,
      hydrationReviewNotes: [],
    };
    const params = buildLoadPersistParamsAfterParseApply(workspaceAtReparse, res, summary, {});
    expect(params.rate).toBe("900");
    expect(params.customerRate).toBe("1350");

    const updateDraft = vi.fn().mockImplementation(async (_id: string, body: { draft_json: Record<string, unknown> }) => ({
      concurrency_version: 2,
      draft_json: body.draft_json,
    }));
    const saved = await persistWorkspaceDraftAfterParse({
      draftId: "draft-cr",
      draftVersion: 1,
      res,
      summary,
      workspaceAtParseStart: workspaceAtReparse,
      status: "draft",
      seed: { loadNumber: "", hazmat: "unset", palletCaseCount: "", customsBrokerId: null, existingInternalNotes: "" },
      updateDraft,
      buildDraftJson: buildWorkspaceDraftJson,
    });
    expect(saved.draft_json?.rate).toBe("900");
    expect(saved.draft_json?.customerRate).toBe("1350");
    expect(parseManualOverrideKeysFromDraftJson(saved.draft_json ?? {}).has("customerRate")).toBe(
      true,
    );

    const reopened = workspaceFieldsFromDraftJson(saved.draft_json ?? {});
    expect(reopened.customerRate).toBe("1350");
    const persisted = parseManualOverrideKeysFromDraftJson(saved.draft_json ?? {});
    const provenance = hydrationStateFromDraftAndParse(reopened, res.extracted, persisted);
    expect(provenance.manualOverrideKeys.has("customerRate")).toBe(true);
  });

  it("does not replace manually edited stops on re-parse", async () => {
    const stops = [
      {
        _key: "s1",
        stop_type: "PICKUP",
        sequence: 0,
        city: "Dallas",
        state_or_province: "TX",
      },
    ];
    const live = {
      rate: "",
      customerRate: "",
      brokerName: "",
      brokerId: null,
      brokerLoadReference: "",
      loadReferences: [],
      brokerContactName: "",
      draftStops: stops,
    };
    const cbs = mkCbs(live);
    const hydration = createEmptyParseHydrationState();
    hydration.stopsRouteManuallyEdited = true;

    const res = emptyRes({
      stops: [{ stop_type: "delivery", sequence: 0, city: "Austin", state_or_province: "TX" }],
    });
    const result = await applyLoadDocumentParseResponse(res, cbs, hydration);
    expect(live.draftStops).toEqual(stops);
    expect(result.hydrationReviewNotes.length).toBeGreaterThan(0);
  });

  it("full commercial review survives re-parse, save draft, and reopen", async () => {
    vi.mocked(resolveBrokerIdentity).mockResolvedValue({ broker_id: 1 } as never);
    vi.mocked(listBrokerContacts).mockResolvedValue({ items: [] } as never);

    const live = {
      rate: "",
      customerRate: "",
      brokerName: "",
      brokerId: null as number | null,
      brokerLoadReference: "",
      loadReferences: [] as { kind: string; value: string; label?: string }[],
      brokerContactName: "",
      draftStops: [] as unknown[],
    };
    const cbs = mkCbs(live);

    const first = await hydrateLoadWorkspaceFromParseResponse(emptyRes(parseA), cbs);
    expect(live.brokerId).toBe(1);
    expect(live.rate).toBe("1000");
    expect(live.brokerLoadReference).toBe("100");
    expect(live.loadReferences).toEqual([{ kind: "po_number", value: "555", label: "PO #" }]);

    const reviewed = {
      ...initialWorkspaceFieldsManual(),
      brokerId: 99,
      brokerNameSnapshot: "Broker B",
      brokerContactId: 5,
      brokerLoadReference: "101",
      loadReferences: [{ kind: "po_number", value: "556", label: "PO #" }],
      rate: "1500",
      driverId: 10,
      truckId: 20,
      trailerAssetId: 30,
    };
    const hydration = first.parseHydrationState;
    markBrokerIdentityLocked(hydration);
    hydration.brokerContactIdManuallySelected = true;
    hydration.loadReferencesManuallyEdited = true;
    registerManualParseFieldEdit(hydration, "brokerLoadReference", "101");
    registerManualParseFieldEdit(hydration, "rate", "1500");
    hydration.manualOverrideKeys.add("brokerLoadReference");
    hydration.manualOverrideKeys.add("rate");

    const workspaceAtReparse = reviewed;
    live.brokerId = reviewed.brokerId;
    live.brokerName = reviewed.brokerNameSnapshot;
    live.brokerLoadReference = reviewed.brokerLoadReference;
    live.loadReferences = reviewed.loadReferences;
    live.rate = reviewed.rate;
    const reparseRes = emptyRes({
      ...parseA,
      rate: 900,
      broker_load_reference: "100",
      references: [{ kind: "po_number", value: "555" }],
    });

    vi.mocked(listBrokerContacts).mockResolvedValue({
      items: [{ id: 5, name: "Contact B" }],
    } as never);

    const second = await hydrateLoadWorkspaceFromParseResponse(
      reparseRes,
      cbs,
      hydration,
      workspaceAtReparse,
    );
    expect(live.brokerId).toBe(99);
    expect(live.rate).toBe("1500");
    expect(live.brokerLoadReference).toBe("101");
    expect(live.loadReferences).toEqual([{ kind: "po_number", value: "556", label: "PO #" }]);
    expect(second.warnings.some((w) => w.includes("Broker A"))).toBe(true);

    const merged = buildLoadPersistParamsAfterParseApply(
      workspaceAtReparse,
      reparseRes,
      second.summary,
      { driverId: 10, truckId: 20, trailerAssetId: 30 },
    );
    const draftJson = buildWorkspaceDraftJson({ ...merged, status: "draft" });
    expect(draftJson.brokerId).toBe(99);
    expect(draftJson.brokerNameSnapshot).toBe("Broker B");
    expect(draftJson.brokerContactId).toBe(5);
    expect(draftJson.brokerLoadReference).toBe("101");
    expect(draftJson.loadReferences).toEqual([{ kind: "po_number", value: "556", label: "PO #" }]);
    expect(draftJson.rate).toBe("1500");
    expect(draftJson.driverId).toBe(10);
    expect(draftJson.truckId).toBe(20);
    expect(draftJson.trailerAssetId).toBe(30);

    const updateDraft = vi.fn().mockImplementation(async (_id: string, body: { draft_json: Record<string, unknown> }) => ({
      concurrency_version: 2,
      draft_json: body.draft_json,
    }));
    const saved = await persistWorkspaceDraftAfterParse({
      draftId: "draft-commercial",
      draftVersion: 1,
      res: reparseRes,
      summary: second.summary,
      workspaceAtParseStart: workspaceAtReparse,
      status: "draft",
      seed: {
        loadNumber: "",
        hazmat: "unset",
        palletCaseCount: "",
        customsBrokerId: null,
        existingInternalNotes: "",
        driverId: 10,
        truckId: 20,
        trailerAssetId: 30,
      },
      updateDraft,
      buildDraftJson: buildWorkspaceDraftJson,
    });

    const reopened = workspaceFieldsFromDraftJson(saved.draft_json ?? {});
    expect(reopened).toMatchObject({
      brokerId: 99,
      brokerNameSnapshot: "Broker B",
      brokerContactId: 5,
      brokerLoadReference: "101",
      rate: "1500",
      driverId: 10,
      truckId: 20,
      trailerAssetId: 30,
    });
    expect(reopened.loadReferences).toEqual([{ kind: "po_number", value: "556", label: "PO #" }]);

    const displayFields = workspaceFieldsFromLoadPersistParams(merged, {
      status: "draft",
      driverId: 10,
      truckId: 20,
      trailerAssetId: 30,
    });
    expect(displayFields.brokerLoadReference).toBe(reopened.brokerLoadReference);
    expect(displayFields.rate).toBe(reopened.rate);

    const provenance = hydrationStateFromDraftAndParse(reopened, reparseRes.extracted);
    expect(provenance.brokerIdentityLocked).toBe(true);
    expect(provenance.loadReferencesManuallyEdited).toBe(true);
    expect(provenance.manualOverrideKeys.has("rate")).toBe(true);
  });

  it("locked broker name survives re-parse in draft_json when parse proposes another name", async () => {
    const live = {
      rate: "",
      customerRate: "",
      brokerName: "Acme Logistics",
      brokerId: 99 as number | null,
      brokerLoadReference: "",
      loadReferences: [] as { kind: string; value: string }[],
      brokerContactName: "",
      draftStops: [] as unknown[],
    };
    const cbs = mkCbs(live);
    const hydration = createEmptyParseHydrationState();
    markBrokerIdentityLocked(hydration);
    const workspace = {
      ...initialWorkspaceFieldsManual(),
      brokerId: 99,
      brokerNameSnapshot: "Acme Logistics",
    };
    const summary = await applyLoadDocumentParseResponse(
      emptyRes({ broker_name_snapshot: "Acme Logistics", broker_mc_number_snapshot: "1" }),
      cbs,
      hydration,
      {
        brokerId: 99,
        brokerNameSnapshot: "Acme Logistics",
        brokerContactId: null,
        loadReferences: [],
        brokerLoadReference: "",
      },
    );
    const reparseRes = emptyRes({
      broker_name_snapshot: "Other Carrier",
      broker_mc_number_snapshot: "1",
    });
    const second = await applyLoadDocumentParseResponse(reparseRes, cbs, summary.parseHydrationState, workspace);
    expect(live.brokerName).toBe("Acme Logistics");
    const draftJson = buildWorkspaceDraftJson({
      ...buildLoadPersistParamsAfterParseApply(workspace, reparseRes, second, {}),
      status: "draft",
    });
    expect(draftJson.brokerId).toBe(99);
    expect(draftJson.brokerNameSnapshot).toBe("Acme Logistics");
    const reopened = workspaceFieldsFromDraftJson(draftJson);
    expect(reopened.brokerNameSnapshot).toBe("Acme Logistics");
    expect(reopened.brokerId).toBe(99);
  });

  it("keeps saved PO/BOL references when re-parse returns an empty reference list", async () => {
    const setLoadReferences = vi.fn();
    const hydration = createEmptyParseHydrationState();
    hydration.loadReferencesManuallyEdited = true;
    const guard = {
      brokerId: null,
      brokerNameSnapshot: "",
      brokerContactId: null,
      brokerLoadReference: "",
      loadReferences: [{ kind: "po_number", value: "556", label: "PO #" }],
    };
    const cbs = mkCbs({
      rate: "",
      brokerName: "",
      brokerId: null,
      brokerLoadReference: "",
      loadReferences: guard.loadReferences,
      brokerContactName: "",
      draftStops: [],
    });
    cbs.setLoadReferences = setLoadReferences;
    await applyLoadDocumentParseResponse(emptyRes({ references: [] }), cbs, hydration, guard);
    expect(setLoadReferences).not.toHaveBeenCalled();

    const params = buildLoadPersistParamsAfterParseApply(
      { ...initialWorkspaceFieldsManual(), loadReferences: guard.loadReferences },
      emptyRes({ references: [] }),
      {
        resolvedBrokerId: null,
        resolvedBrokerContactId: null,
        brokerContactMatched: false,
        mcOrDotAttempted: false,
        unresolvedStopCount: 0,
        parseHydrationState: hydration,
        hydrationReviewNotes: [],
      },
      {},
    );
    expect(params.loadReferences).toEqual(guard.loadReferences);
  });
});
