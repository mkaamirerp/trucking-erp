import { describe, expect, it, vi } from "vitest";
import {
  applyParseScalarHydration,
  createEmptyParseHydrationState,
  registerManualParseFieldEdit,
} from "./loadParseHydrationState";
import type { ApplyLoadDocumentParseCallbacks } from "./applyLoadDocumentParseResponse";
import { buildWorkspaceDraftJson } from "./loadWorkspaceShared";
import { persistWorkspaceDraftAfterParse } from "./applyLoadDocumentParseResponse";
import { createEmptyParseHydrationState as emptySummaryState } from "./loadParseHydrationState";

function mkCbs() {
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
  } satisfies ApplyLoadDocumentParseCallbacks;
}

describe("re-parse manual override retention", () => {
  it("does not re-apply a manually corrected scalar on the next parse", () => {
    const cbs = mkCbs();
    let state = createEmptyParseHydrationState();
    state = applyParseScalarHydration({ rate: 1000 } as never, cbs, state);
    registerManualParseFieldEdit(state, "rate", "1500");
    vi.mocked(cbs.setRate).mockClear();
    state = applyParseScalarHydration({ rate: 2000, commodity: "Widgets" } as never, cbs, state);
    expect(cbs.setRate).not.toHaveBeenCalled();
    expect(cbs.setCommodity).toHaveBeenCalledWith("Widgets");
    expect(state.manualOverrideKeys.has("rate")).toBe(true);
  });
});

describe("persistWorkspaceDraftAfterParse assignment seed", () => {
  it("includes driver, truck, and trailer from seed in draft_json", async () => {
    const updateDraft = vi.fn().mockImplementation(async (_id: string, body: { draft_json: Record<string, unknown> }) => ({
      concurrency_version: 2,
      draft_json: body.draft_json,
    }));
    const saved = await persistWorkspaceDraftAfterParse({
      draftId: "d1",
      draftVersion: 1,
      res: {
        document: { filename: "t.pdf" },
        extracted: { references: [], stops: [], rate: 500 },
        raw_text: "",
        warnings: [],
        field_confidence: {},
      },
      summary: {
        resolvedBrokerId: null,
        resolvedBrokerContactId: null,
        brokerContactMatched: false,
        mcOrDotAttempted: false,
        unresolvedStopCount: 0,
        parseHydrationState: emptySummaryState(),
      },
      status: "draft",
      seed: {
        loadNumber: "",
        hazmat: "unset",
        palletCaseCount: "",
        customsBrokerId: null,
        existingInternalNotes: "",
        driverId: 42,
        truckId: 7,
        trailerAssetId: 3,
      },
      updateDraft,
      buildDraftJson: (params) => buildWorkspaceDraftJson(params),
    });
    expect(saved.draft_json).toMatchObject({ driverId: 42, truckId: 7, trailerAssetId: 3 });
  });
});
