import { describe, expect, it, vi } from "vitest";
import {
  applyEmptyWorkspaceFieldsFromParseResponse,
  applyLoadDocumentParseResponse,
  buildLoadPersistParamsFromParseResponse,
  persistWorkspaceDraftAfterParse,
} from "./applyLoadDocumentParseResponse";
import type { LoadDocumentParseResponse } from "@/api";
import { createEmptyParseHydrationState } from "@/loadWorkspace/loadParseHydrationState";
import { buildWorkspaceDraftJson, initialWorkspaceFieldsManual } from "@/loadWorkspace/loadWorkspaceShared";

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
    };
    await expect(
      persistWorkspaceDraftAfterParse({
        draftId: "draft-1",
        draftVersion: 2,
        res: emptyRes({ broker_load_reference: "3872125-1" }),
        summary,
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
    };
    const saved = await persistWorkspaceDraftAfterParse({
      draftId: "draft-1",
      draftVersion: 2,
      res: emptyRes({ broker_load_reference: "3872125-1" }),
      summary,
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
      status: "draft",
      seed: { loadNumber: "", hazmat: "unset", palletCaseCount: "", customsBrokerId: null, existingInternalNotes: "" },
      updateDraft,
      buildDraftJson: buildWorkspaceDraftJson,
    })).rejects.toThrow("not preserved");
  });

});
