import { describe, expect, it, vi } from "vitest";
import {
  applyEmptyWorkspaceFieldsFromParseResponse,
  applyLoadDocumentParseResponse,
  buildLoadPersistParamsAfterParseApply,
  buildLoadPersistParamsFromParseResponse,
  persistWorkspaceDraftAfterParse,
  type ApplyLoadDocumentParseSummary,
} from "./applyLoadDocumentParseResponse";
import type { LoadDocumentParseResponse } from "@/api";
import {
  createEmptyParseHydrationState,
  markBrokerIdentityLocked,
} from "@/loadWorkspace/loadParseHydrationState";
import { buildWorkspaceDraftJson, initialWorkspaceFieldsManual } from "@/loadWorkspace/loadWorkspaceShared";
import { listBrokerContacts, resolveBrokerIdentity } from "@/api";

vi.mock("@/api", () => ({
  resolveBrokerIdentity: vi.fn(),
  listBrokerContacts: vi.fn(),
}));

function emptyRes(over: Partial<LoadDocumentParseResponse["extracted"]> = {}): LoadDocumentParseResponse {
  return {
    document: { filename: "t.pdf" },
    raw_text: "",
    warnings: [],
    field_confidence: {},
    extracted: {
      references: [],
      stops: [],
      ...over,
    },
  };
}

describe("applyLoadDocumentParseResponse references", () => {
  it("copies extracted.references into workspace state and does not put generic refs on stops", async () => {
    const setLoadReferences = vi.fn();
    const setDraftStops = vi.fn();
    const cbs = {
      setBrokerNameSnapshot: vi.fn(),
      setBrokerId: vi.fn(),
      setBrokerContactId: vi.fn(),
      setBrokerContacts: vi.fn(),
      setBrokerContactNameSnapshot: vi.fn(),
      setBrokerContactPhoneSnapshot: vi.fn(),
      setBrokerContactEmailSnapshot: vi.fn(),
      setBrokerLoadReference: vi.fn(),
      setLoadReferences,
      setFreightMode: vi.fn(),
      setEquipmentType: vi.fn(),
      setTrailerType: vi.fn(),
      setTrailerSize: vi.fn(),
      setCommodity: vi.fn(),
      setEstimatedWeight: vi.fn(),
      setTemperatureRequirement: vi.fn(),
      setRate: vi.fn(),
      setCustomerRate: vi.fn(),
      setMiles: vi.fn(),
      setInternalNotes: vi.fn(),
      setDraftStops,
    };
    await applyLoadDocumentParseResponse(
      emptyRes({
        references: [
          { kind: "pickup_number", value: "PU-GENERIC" },
          { kind: "po_number", value: "PO-1" },
        ],
        stops: [
          { stop_type: "pickup", sequence: 0, city: "Dallas" },
          { stop_type: "delivery", sequence: 1, city: "Houston", reference_number: "STOP-OWNED" },
        ],
      }),
      cbs,
    );
    expect(setLoadReferences).toHaveBeenCalledWith([
      { kind: "pickup_number", value: "PU-GENERIC" },
      { kind: "po_number", value: "PO-1" },
    ]);
    const draft = setDraftStops.mock.calls[0][0];
    expect(draft[0].reference_number).toBeNull();
    expect(draft[1].reference_number).toBe("STOP-OWNED");
    expect(draft.some((s: { reference_number?: string | null }) => s.reference_number === "PU-GENERIC")).toBe(
      false,
    );
  });

  it("Issue I19: unknown parser stop types stay UNRESOLVED with evidence", async () => {
    const setDraftStops = vi.fn();
    const cbs = {
      setBrokerNameSnapshot: vi.fn(),
      setBrokerId: vi.fn(),
      setBrokerContactId: vi.fn(),
      setBrokerContacts: vi.fn(),
      setBrokerContactNameSnapshot: vi.fn(),
      setBrokerContactPhoneSnapshot: vi.fn(),
      setBrokerContactEmailSnapshot: vi.fn(),
      setBrokerLoadReference: vi.fn(),
      setLoadReferences: vi.fn(),
      setFreightMode: vi.fn(),
      setEquipmentType: vi.fn(),
      setTrailerType: vi.fn(),
      setTrailerSize: vi.fn(),
      setCommodity: vi.fn(),
      setEstimatedWeight: vi.fn(),
      setTemperatureRequirement: vi.fn(),
      setRate: vi.fn(),
      setCustomerRate: vi.fn(),
      setMiles: vi.fn(),
      setInternalNotes: vi.fn(),
      setDraftStops,
    };
    const summary = await applyLoadDocumentParseResponse(
      emptyRes({
        stops: [{ stop_type: "other", sequence: 0, city: "Dallas" }],
      }),
      cbs,
    );
    expect(summary.unresolvedStopCount).toBe(1);
    const draft = setDraftStops.mock.calls[0][0];
    expect(draft[0].stop_type).toBe("UNRESOLVED");
    expect(draft[0].parseStopTypeEvidence).toBe("other");
  });

  it("Issue I18: second document clears parse-owned commodity when omitted", async () => {
    const setCommodity = vi.fn();
    const cbs = {
      setBrokerNameSnapshot: vi.fn(),
      setBrokerId: vi.fn(),
      setBrokerContactId: vi.fn(),
      setBrokerContacts: vi.fn(),
      setBrokerContactNameSnapshot: vi.fn(),
      setBrokerContactPhoneSnapshot: vi.fn(),
      setBrokerContactEmailSnapshot: vi.fn(),
      setBrokerLoadReference: vi.fn(),
      setLoadReferences: vi.fn(),
      setFreightMode: vi.fn(),
      setEquipmentType: vi.fn(),
      setTrailerType: vi.fn(),
      setTrailerSize: vi.fn(),
      setCommodity,
      setEstimatedWeight: vi.fn(),
      setTemperatureRequirement: vi.fn(),
      setRate: vi.fn(),
      setCustomerRate: vi.fn(),
      setMiles: vi.fn(),
      setInternalNotes: vi.fn(),
      setDraftStops: vi.fn(),
    };
    const first = await applyLoadDocumentParseResponse(emptyRes({ commodity: "Steel" }), cbs);
    expect(setCommodity).toHaveBeenCalledWith("Steel");
    setCommodity.mockClear();
    await applyLoadDocumentParseResponse(emptyRes({}), cbs, first.parseHydrationState);
    expect(setCommodity).toHaveBeenCalledWith("");
  });

  it("Issue I18: manual commodity override survives second parse omitting commodity", async () => {
    const setCommodity = vi.fn();
    const cbs = {
      setBrokerNameSnapshot: vi.fn(),
      setBrokerId: vi.fn(),
      setBrokerContactId: vi.fn(),
      setBrokerContacts: vi.fn(),
      setBrokerContactNameSnapshot: vi.fn(),
      setBrokerContactPhoneSnapshot: vi.fn(),
      setBrokerContactEmailSnapshot: vi.fn(),
      setBrokerLoadReference: vi.fn(),
      setLoadReferences: vi.fn(),
      setFreightMode: vi.fn(),
      setEquipmentType: vi.fn(),
      setTrailerType: vi.fn(),
      setTrailerSize: vi.fn(),
      setCommodity,
      setEstimatedWeight: vi.fn(),
      setTemperatureRequirement: vi.fn(),
      setRate: vi.fn(),
      setCustomerRate: vi.fn(),
      setMiles: vi.fn(),
      setInternalNotes: vi.fn(),
      setDraftStops: vi.fn(),
    };
    const first = await applyLoadDocumentParseResponse(emptyRes({ commodity: "Steel" }), cbs);
    first.parseHydrationState.manualOverrideKeys.add("commodity");
    setCommodity.mockClear();
    await applyLoadDocumentParseResponse(emptyRes({ rate: 100 }), cbs, first.parseHydrationState);
    expect(setCommodity).not.toHaveBeenCalled();
  });

  it("Issue I7: does not write raw_text into internal notes", async () => {
    const setInternalNotes = vi.fn();
    const cbs = {
      setBrokerNameSnapshot: vi.fn(),
      setBrokerId: vi.fn(),
      setBrokerContactId: vi.fn(),
      setBrokerContacts: vi.fn(),
      setBrokerContactNameSnapshot: vi.fn(),
      setBrokerContactPhoneSnapshot: vi.fn(),
      setBrokerContactEmailSnapshot: vi.fn(),
      setBrokerLoadReference: vi.fn(),
      setLoadReferences: vi.fn(),
      setFreightMode: vi.fn(),
      setEquipmentType: vi.fn(),
      setTrailerType: vi.fn(),
      setTrailerSize: vi.fn(),
      setCommodity: vi.fn(),
      setEstimatedWeight: vi.fn(),
      setTemperatureRequirement: vi.fn(),
      setRate: vi.fn(),
      setCustomerRate: vi.fn(),
      setMiles: vi.fn(),
      setInternalNotes,
      setDraftStops: vi.fn(),
    };
    await applyLoadDocumentParseResponse(
      { ...emptyRes(), raw_text: "FULL PDF TEXT SHOULD NOT BECOME NOTES" },
      cbs,
    );
    expect(setInternalNotes).not.toHaveBeenCalled();
  });
});

function mockParseCallbacks() {
  return {
    setBrokerNameSnapshot: vi.fn(),
    setBrokerId: vi.fn(),
    setBrokerContactId: vi.fn(),
    setBrokerContacts: vi.fn(),
    setBrokerContactNameSnapshot: vi.fn(),
    setBrokerContactPhoneSnapshot: vi.fn(),
    setBrokerContactEmailSnapshot: vi.fn(),
    setBrokerLoadReference: vi.fn(),
    setLoadReferences: vi.fn(),
    setFreightMode: vi.fn(),
    setEquipmentType: vi.fn(),
    setTrailerType: vi.fn(),
    setTrailerSize: vi.fn(),
    setCommodity: vi.fn(),
    setEstimatedWeight: vi.fn(),
    setTemperatureRequirement: vi.fn(),
    setRate: vi.fn(),
    setCustomerRate: vi.fn(),
    setMiles: vi.fn(),
    setInternalNotes: vi.fn(),
    setDraftStops: vi.fn(),
  };
}

describe("applyEmptyWorkspaceFieldsFromParseResponse", () => {
  it("fills broker load reference when draft_json left it empty but broker name is set", () => {
    const cbs = mockParseCallbacks();
    const fields = {
      ...initialWorkspaceFieldsManual(),
      brokerNameSnapshot: "Armstrong Transport",
      brokerLoadReference: "",
      rate: "1200",
    };
    applyEmptyWorkspaceFieldsFromParseResponse(
      fields,
      emptyRes({ broker_load_reference: "3872125-1" }),
      cbs,
    );
    expect(cbs.setBrokerLoadReference).toHaveBeenCalledWith("3872125-1");
    expect(cbs.setBrokerNameSnapshot).not.toHaveBeenCalled();
    expect(cbs.setRate).not.toHaveBeenCalled();
  });

  it("does not overwrite an existing broker load reference", () => {
    const cbs = mockParseCallbacks();
    const fields = {
      ...initialWorkspaceFieldsManual(),
      brokerLoadReference: "KEEP-ME",
    };
    applyEmptyWorkspaceFieldsFromParseResponse(
      fields,
      emptyRes({ broker_load_reference: "3872125-1" }),
      cbs,
    );
    expect(cbs.setBrokerLoadReference).not.toHaveBeenCalled();
  });

  it("does not resurrect intentionally cleared scalars saved on draft_json", () => {
    const cbs = mockParseCallbacks();
    const fields = {
      ...initialWorkspaceFieldsManual(),
      rate: "",
      brokerLoadReference: "",
      brokerContactNameSnapshot: "",
      commodity: "",
    };
    const draftJson = buildWorkspaceDraftJson({
      ...initialWorkspaceFieldsManual(),
      rate: "",
      brokerLoadReference: "",
      brokerContactNameSnapshot: "",
      commodity: "",
      mode: "",
      status: "draft",
    });
    applyEmptyWorkspaceFieldsFromParseResponse(
      fields,
      emptyRes({
        rate: 1200,
        broker_load_reference: "REF-9",
        broker_contact_name_snapshot: "Sam",
        commodity: "Steel",
      }),
      cbs,
      draftJson,
    );
    expect(cbs.setRate).not.toHaveBeenCalled();
    expect(cbs.setBrokerLoadReference).not.toHaveBeenCalled();
    expect(cbs.setBrokerContactNameSnapshot).not.toHaveBeenCalled();
    expect(cbs.setCommodity).not.toHaveBeenCalled();
  });
});

describe("buildLoadPersistParamsFromParseResponse", () => {
  it("carries draft-only proposed assignment from seed through draft_json build", async () => {
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: createEmptyParseHydrationState(),
      hydrationReviewNotes: [],
    };
    const params = buildLoadPersistParamsFromParseResponse(emptyRes(), summary, {
      driverId: 30,
      truckId: 6,
      trailerAssetId: 2,
    });
    const json = buildWorkspaceDraftJson({ ...params, status: "draft" });
    expect(json).toMatchObject({ driverId: 30, truckId: 6, trailerAssetId: 2 });
  });
});

describe("persistWorkspaceDraftAfterParse", () => {
  it("awaits draft_json persist and surfaces failures", async () => {
    const updateDraft = vi.fn().mockRejectedValue(new Error("network down"));
    const buildDraftJson = vi.fn().mockReturnValue({ loadNumber: "X" });
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: createEmptyParseHydrationState(),
      hydrationReviewNotes: [],
    };
    await expect(
      persistWorkspaceDraftAfterParse({
        draftId: "draft-1",
        draftVersion: 2,
        res: emptyRes({ broker_load_reference: "3872125-1" }),
        summary,
        workspaceAtParseStart: initialWorkspaceFieldsManual(),
        status: "draft",
        seed: {
          loadNumber: "",
          hazmat: "unset",
          palletCaseCount: "",
          customsBrokerId: null,
          existingInternalNotes: "",
        },
        updateDraft,
        buildDraftJson,
      }),
    ).rejects.toThrow("network down");
    expect(updateDraft).toHaveBeenCalledOnce();
  });

  it("returns saved draft metadata on success", async () => {
    const updateDraft = vi.fn().mockResolvedValue({
      concurrency_version: 3,
      draft_json: { brokerLoadReference: "3872125-1" },
    });
    const buildDraftJson = vi.fn().mockReturnValue({ brokerLoadReference: "3872125-1" });
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: createEmptyParseHydrationState(),
      hydrationReviewNotes: [],
    };
    const saved = await persistWorkspaceDraftAfterParse({
      draftId: "draft-1",
      draftVersion: 2,
      res: emptyRes({ broker_load_reference: "3872125-1" }),
      summary,
      workspaceAtParseStart: initialWorkspaceFieldsManual(),
      status: "draft",
      seed: {
        loadNumber: "",
        hazmat: "unset",
        palletCaseCount: "",
        customsBrokerId: null,
        existingInternalNotes: "",
      },
      updateDraft,
      buildDraftJson,
    });
    expect(saved.concurrency_version).toBe(3);
    expect(saved.draft_json?.brokerLoadReference).toBe("3872125-1");
  });
  it("persists reviewed Chicago pickup and Reidsville delivery in the post-parse draft save", async () => {
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: createEmptyParseHydrationState(),
      hydrationReviewNotes: [],
    };
    const updateDraft = vi.fn().mockImplementation(async (_id: string, body: { draft_json: Record<string, unknown> }) => ({
      concurrency_version: 3,
      draft_json: body.draft_json,
    }));
    const saved = await persistWorkspaceDraftAfterParse({
      draftId: "armstrong-review-draft",
      draftVersion: 2,
      res: emptyRes({
        broker_load_reference: "3872125-1",
        rate: 1800,
        stops: [
          { stop_type: "pickup", sequence: 0, city: "Chicago", state_or_province: "IL" },
          { stop_type: "delivery", sequence: 1, city: "Reidsville", state_or_province: "NC" },
        ],
      }),
      summary,
      workspaceAtParseStart: initialWorkspaceFieldsManual(),
      status: "draft",
      seed: { loadNumber: "", hazmat: "unset", palletCaseCount: "", customsBrokerId: null, existingInternalNotes: "" },
      updateDraft,
      buildDraftJson: buildWorkspaceDraftJson,
    });
    const stops = saved.draft_json?.draftStops as Array<Record<string, unknown>>;
    expect(stops).toHaveLength(2);
    expect(stops.map((s) => [s.stop_type, s.city, s.state_or_province])).toEqual([
      ["PICKUP", "Chicago", "IL"],
      ["DELIVERY", "Reidsville", "NC"],
    ]);
    expect(updateDraft).toHaveBeenCalledOnce();
  });

  it("rejects a successful-looking draft response that silently discarded parsed stops", async () => {
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: createEmptyParseHydrationState(),
      hydrationReviewNotes: [],
    };
    const updateDraft = vi.fn().mockImplementation(async (_id: string, body: { draft_json: Record<string, unknown> }) => ({
      concurrency_version: 3,
      draft_json: { ...body.draft_json, draftStops: [] },
    }));
    await expect(persistWorkspaceDraftAfterParse({
      draftId: "armstrong-review-draft",
      draftVersion: 2,
      res: emptyRes({
        stops: [
          { stop_type: "pickup", sequence: 0, city: "Chicago", state_or_province: "IL" },
          { stop_type: "delivery", sequence: 1, city: "Reidsville", state_or_province: "NC" },
        ],
      }),
      summary,
      workspaceAtParseStart: initialWorkspaceFieldsManual(),
      status: "draft",
      seed: { loadNumber: "", hazmat: "unset", palletCaseCount: "", customsBrokerId: null, existingInternalNotes: "" },
      updateDraft,
      buildDraftJson: buildWorkspaceDraftJson,
    })).rejects.toThrow("not preserved");
  });

  it("rejects altered parsed stop locations in the echoed saved draft, not just zero rows", async () => {
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: createEmptyParseHydrationState(),
      hydrationReviewNotes: [],
    };
    const updateDraft = vi.fn().mockImplementation(async (_id: string, body: { draft_json: Record<string, unknown> }) => {
      const rows = body.draft_json.draftStops as Array<Record<string, unknown>>;
      return {
        concurrency_version: 3,
        draft_json: { ...body.draft_json, draftStops: [{ ...rows[0], city: "Wrong" }, rows[1]] },
      };
    });
    await expect(persistWorkspaceDraftAfterParse({
      draftId: "armstrong-review-draft",
      draftVersion: 2,
      res: emptyRes({
        stops: [
          { stop_type: "pickup", sequence: 0, city: "Chicago", state_or_province: "IL" },
          { stop_type: "delivery", sequence: 1, city: "Reidsville", state_or_province: "NC" },
        ],
      }),
      summary,
      workspaceAtParseStart: initialWorkspaceFieldsManual(),
      status: "draft",
      seed: { loadNumber: "", hazmat: "unset", palletCaseCount: "", customsBrokerId: null, existingInternalNotes: "" },
      updateDraft,
      buildDraftJson: buildWorkspaceDraftJson,
    })).rejects.toThrow("not preserved");
  });

  it("uses workspace snapshot for manual scalar overrides instead of parse extract", () => {
    const hydration = createEmptyParseHydrationState();
    hydration.manualOverrideKeys.add("rate");
    const summary = {
      resolvedBrokerId: null,
      resolvedBrokerContactId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
      unresolvedStopCount: 0,
      parseHydrationState: hydration,
      hydrationReviewNotes: [],
    };
    const workspaceAtParseStart = { ...initialWorkspaceFieldsManual(), rate: "1500" };
    const params = buildLoadPersistParamsAfterParseApply(
      workspaceAtParseStart,
      emptyRes({ rate: 900 }),
      summary,
      {},
    );
    expect(params.rate).toBe("1500");
  });

  it("keeps locked broker id/name and reviewed references from workspace snapshot", () => {
    const hydration = createEmptyParseHydrationState();
    markBrokerIdentityLocked(hydration);
    hydration.brokerContactIdManuallySelected = true;
    hydration.manualOverrideKeys.add("brokerLoadReference");
    hydration.loadReferencesManuallyEdited = true;
    hydration.manualOverrideKeys.add("rate");
    const summary = {
      resolvedBrokerId: 99,
      resolvedBrokerContactId: 5,
      brokerContactMatched: true,
      mcOrDotAttempted: true,
      unresolvedStopCount: 0,
      parseHydrationState: hydration,
      hydrationReviewNotes: [],
    };
    const workspaceAtParseStart = {
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
    const params = buildLoadPersistParamsAfterParseApply(
      workspaceAtParseStart,
      emptyRes({
        broker_name_snapshot: "Broker A",
        broker_load_reference: "100",
        references: [{ kind: "po_number", value: "555" }],
        rate: 900,
      }),
      summary,
      { driverId: 10, truckId: 20, trailerAssetId: 30 },
    );
    expect(params.brokerId).toBe(99);
    expect(params.brokerNameSnapshot).toBe("Broker B");
    expect(params.brokerContactId).toBe(5);
    expect(params.brokerLoadReference).toBe("101");
    expect(params.loadReferences).toEqual([{ kind: "po_number", value: "556", label: "PO #" }]);
    expect(params.rate).toBe("1500");
  });
});

describe("applyLoadDocumentParseResponse broker identity", () => {
  it("clears manual contact when parser resolves a different broker", async () => {
    vi.mocked(resolveBrokerIdentity).mockResolvedValue({ broker_id: 2 } as never);
    vi.mocked(listBrokerContacts).mockResolvedValue({
      items: [{ id: 20, name: "Contact B" }],
    } as never);
    const setBrokerContactId = vi.fn();
    const hydration = createEmptyParseHydrationState();
    hydration.brokerContactIdManuallySelected = true;
    const guard = {
      brokerId: 1,
      brokerNameSnapshot: "Broker A",
      brokerContactId: 10,
      loadReferences: [],
      brokerLoadReference: "",
    };
    const cbs = {
      setBrokerNameSnapshot: vi.fn(),
      setBrokerId: vi.fn(),
      setBrokerContactId,
      setBrokerContacts: vi.fn(),
      setBrokerContactNameSnapshot: vi.fn(),
      setBrokerContactPhoneSnapshot: vi.fn(),
      setBrokerContactEmailSnapshot: vi.fn(),
      setBrokerLoadReference: vi.fn(),
      setLoadReferences: vi.fn(),
      setFreightMode: vi.fn(),
      setEquipmentType: vi.fn(),
      setTrailerType: vi.fn(),
      setTrailerSize: vi.fn(),
      setCommodity: vi.fn(),
      setEstimatedWeight: vi.fn(),
      setTemperatureRequirement: vi.fn(),
      setRate: vi.fn(),
      setCustomerRate: vi.fn(),
      setMiles: vi.fn(),
      setInternalNotes: vi.fn(),
      setDraftStops: vi.fn(),
    };
    const result = await applyLoadDocumentParseResponse(
      emptyRes({
        broker_mc_number_snapshot: "999",
        broker_name_snapshot: "Broker B",
      }),
      cbs,
      hydration,
      guard,
    );
    expect(setBrokerContactId).toHaveBeenCalledWith(null);
    expect(result.resolvedBrokerContactId).toBeNull();
    expect(result.parseHydrationState.brokerContactIdManuallySelected).toBe(false);
    expect(result.hydrationReviewNotes.some((n) => n.includes("contact"))).toBe(true);
  });

  it("skips MC/DOT broker resolution when broker identity is locked", async () => {
    vi.mocked(resolveBrokerIdentity).mockResolvedValue({ broker_id: 1 } as never);
    const setBrokerId = vi.fn();
    const hydration = createEmptyParseHydrationState();
    hydration.brokerIdentityLocked = true;
    const guard = {
      brokerId: 99,
      brokerNameSnapshot: "Broker B",
      brokerContactId: null,
      loadReferences: [],
      brokerLoadReference: "",
    };
    const cbs = {
      setBrokerNameSnapshot: vi.fn(),
      setBrokerId,
      setBrokerContactId: vi.fn(),
      setBrokerContacts: vi.fn(),
      setBrokerContactNameSnapshot: vi.fn(),
      setBrokerContactPhoneSnapshot: vi.fn(),
      setBrokerContactEmailSnapshot: vi.fn(),
      setBrokerLoadReference: vi.fn(),
      setLoadReferences: vi.fn(),
      setFreightMode: vi.fn(),
      setEquipmentType: vi.fn(),
      setTrailerType: vi.fn(),
      setTrailerSize: vi.fn(),
      setCommodity: vi.fn(),
      setEstimatedWeight: vi.fn(),
      setTemperatureRequirement: vi.fn(),
      setRate: vi.fn(),
      setCustomerRate: vi.fn(),
      setMiles: vi.fn(),
      setInternalNotes: vi.fn(),
      setDraftStops: vi.fn(),
    };
    const result = await applyLoadDocumentParseResponse(
      emptyRes({
        broker_mc_number_snapshot: "123456",
        broker_name_snapshot: "Broker A",
      }),
      cbs,
      hydration,
      guard,
    );
    expect(setBrokerId).not.toHaveBeenCalled();
    expect(result.resolvedBrokerId).toBe(99);
    expect(result.hydrationReviewNotes.some((n) => n.includes("Broker A"))).toBe(true);
  });
});

describe("contact id in persisted draft_json", () => {
  const mkCbs = () => ({
    setBrokerNameSnapshot: vi.fn(),
    setBrokerId: vi.fn(),
    setBrokerContactId: vi.fn(),
    setBrokerContacts: vi.fn(),
    setBrokerContactNameSnapshot: vi.fn(),
    setBrokerContactPhoneSnapshot: vi.fn(),
    setBrokerContactEmailSnapshot: vi.fn(),
    setBrokerLoadReference: vi.fn(),
    setLoadReferences: vi.fn(),
    setFreightMode: vi.fn(),
    setEquipmentType: vi.fn(),
    setTrailerType: vi.fn(),
    setTrailerSize: vi.fn(),
    setCommodity: vi.fn(),
    setEstimatedWeight: vi.fn(),
    setTemperatureRequirement: vi.fn(),
    setRate: vi.fn(),
    setCustomerRate: vi.fn(),
    setMiles: vi.fn(),
    setInternalNotes: vi.fn(),
    setDraftStops: vi.fn(),
  });

  async function draftContactIdAfterParseApply(
    apply: () => Promise<ApplyLoadDocumentParseSummary>,
    workspaceAtParseStart: ReturnType<typeof initialWorkspaceFieldsManual> & {
      brokerId?: number | null;
      brokerContactId?: number | null;
      brokerNameSnapshot?: string;
    },
    res: LoadDocumentParseResponse,
  ): Promise<number | null> {
    const summary = await apply();
    const params = buildLoadPersistParamsAfterParseApply(workspaceAtParseStart, res, summary, {});
    const json = buildWorkspaceDraftJson({ ...params, status: "draft" });
    return (json.brokerContactId ?? null) as number | null;
  }

  it("locked broker + invalid contact clears contact in saved draft_json", async () => {
    vi.mocked(resolveBrokerIdentity).mockResolvedValue({ broker_id: 99 } as never);
    vi.mocked(listBrokerContacts).mockResolvedValue({ items: [{ id: 50, name: "Other" }] } as never);
    const hydration = createEmptyParseHydrationState();
    hydration.brokerIdentityLocked = true;
    hydration.brokerContactIdManuallySelected = true;
    const workspace = {
      ...initialWorkspaceFieldsManual(),
      brokerId: 99,
      brokerNameSnapshot: "Broker B",
      brokerContactId: 10,
    };
    const guard = {
      brokerId: 99,
      brokerNameSnapshot: "Broker B",
      brokerContactId: 10,
      loadReferences: [],
      brokerLoadReference: "",
    };
    const id = await draftContactIdAfterParseApply(
      () =>
        applyLoadDocumentParseResponse(
          emptyRes({ broker_mc_number_snapshot: "1", broker_name_snapshot: "Broker B" }),
          mkCbs(),
          hydration,
          guard,
        ),
      workspace,
      emptyRes({ broker_mc_number_snapshot: "1" }),
    );
    expect(id).toBeNull();
  });

  it("parser broker change with no matching contact leaves saved contact null", async () => {
    vi.mocked(resolveBrokerIdentity).mockResolvedValue({ broker_id: 2 } as never);
    vi.mocked(listBrokerContacts).mockResolvedValue({ items: [] } as never);
    const hydration = createEmptyParseHydrationState();
    hydration.brokerContactIdManuallySelected = true;
    const workspace = {
      ...initialWorkspaceFieldsManual(),
      brokerId: 1,
      brokerContactId: 10,
    };
    const guard = {
      brokerId: 1,
      brokerNameSnapshot: "A",
      brokerContactId: 10,
      loadReferences: [],
      brokerLoadReference: "",
    };
    const id = await draftContactIdAfterParseApply(
      () =>
        applyLoadDocumentParseResponse(
          emptyRes({ broker_mc_number_snapshot: "9", broker_name_snapshot: "B" }),
          mkCbs(),
          hydration,
          guard,
        ),
      workspace,
      emptyRes({ broker_mc_number_snapshot: "9" }),
    );
    expect(id).toBeNull();
  });

  it("locked broker + valid belonging contact is preserved in draft_json", async () => {
    vi.mocked(resolveBrokerIdentity).mockResolvedValue({ broker_id: 99 } as never);
    vi.mocked(listBrokerContacts).mockResolvedValue({
      items: [{ id: 10, name: "Contact A" }],
    } as never);
    const hydration = createEmptyParseHydrationState();
    hydration.brokerIdentityLocked = true;
    hydration.brokerContactIdManuallySelected = true;
    const workspace = {
      ...initialWorkspaceFieldsManual(),
      brokerId: 99,
      brokerNameSnapshot: "Broker B",
      brokerContactId: 10,
    };
    const guard = {
      brokerId: 99,
      brokerNameSnapshot: "Broker B",
      brokerContactId: 10,
      loadReferences: [],
      brokerLoadReference: "",
    };
    const id = await draftContactIdAfterParseApply(
      () =>
        applyLoadDocumentParseResponse(
          emptyRes({ broker_mc_number_snapshot: "1", broker_name_snapshot: "Broker B" }),
          mkCbs(),
          hydration,
          guard,
        ),
      workspace,
      emptyRes({ broker_mc_number_snapshot: "1" }),
    );
    expect(id).toBe(10);
  });

  it("contact lookup failure does not persist unverified contact", async () => {
    vi.mocked(resolveBrokerIdentity).mockResolvedValue({ broker_id: 99 } as never);
    vi.mocked(listBrokerContacts).mockRejectedValue(new Error("network"));
    const hydration = createEmptyParseHydrationState();
    hydration.brokerIdentityLocked = true;
    hydration.brokerContactIdManuallySelected = true;
    const workspace = {
      ...initialWorkspaceFieldsManual(),
      brokerId: 99,
      brokerContactId: 10,
    };
    const guard = {
      brokerId: 99,
      brokerNameSnapshot: "Broker B",
      brokerContactId: 10,
      loadReferences: [],
      brokerLoadReference: "",
    };
    const summary = await applyLoadDocumentParseResponse(
      emptyRes({ broker_mc_number_snapshot: "1" }),
      mkCbs(),
      hydration,
      guard,
    );
    expect(summary.resolvedBrokerContactId).toBeNull();
    expect(summary.hydrationReviewNotes.some((n) => n.includes("verify"))).toBe(true);
    const params = buildLoadPersistParamsAfterParseApply(workspace, emptyRes({}), summary, {});
    expect(params.brokerContactId).toBeNull();
  });

  it("initial parse auto-match does not mark manual contact selection", async () => {
    vi.mocked(resolveBrokerIdentity).mockResolvedValue({ broker_id: 1 } as never);
    vi.mocked(listBrokerContacts).mockResolvedValue({
      items: [{ id: 7, name: "Sam", email: "sam@x.com", phone: "" }],
    } as never);
    const hydration = createEmptyParseHydrationState();
    const summary = await applyLoadDocumentParseResponse(
      emptyRes({
        broker_mc_number_snapshot: "1",
        broker_contact_name_snapshot: "Sam",
        broker_contact_email_snapshot: "sam@x.com",
      }),
      mkCbs(),
      hydration,
    );
    expect(summary.resolvedBrokerContactId).toBe(7);
    expect(summary.parseHydrationState.brokerContactIdManuallySelected).toBe(false);
  });
});
