import { describe, expect, it, vi } from "vitest";
import type { LoadDocumentParseResponse } from "@/api";
import {
  applyLoadDocumentParseResponse,
  buildLoadPersistParamsAfterParseApply,
  persistWorkspaceDraftAfterParse,
} from "./applyLoadDocumentParseResponse";
import type { ApplyLoadDocumentParseCallbacks } from "./applyLoadDocumentParseResponse";
import {
  applyParseScalarHydration,
  createEmptyParseHydrationState,
  hydrationStateFromDraftAndParse,
  inferParseContactConfidenceManualKeys,
  registerManualParseFieldEdit,
} from "./loadParseHydrationState";
import {
  buildWorkspaceDraftJson,
  initialWorkspaceFieldsManual,
  workspaceFieldsFromDraftJson,
} from "./loadWorkspaceShared";

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
  brokerName: string;
  brokerContactName: string;
  draftStops: unknown[];
}) {
  return {
    setBrokerNameSnapshot: vi.fn((v: string) => {
      state.brokerName = v;
    }),
    setBrokerId: vi.fn(),
    setBrokerContactId: vi.fn(),
    setBrokerContacts: vi.fn(),
    setBrokerContactNameSnapshot: vi.fn((v: string) => {
      state.brokerContactName = v;
    }),
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
    setRate: vi.fn((v: string) => {
      state.rate = v;
    }),
    setCustomerRate: vi.fn(),
    setMiles: vi.fn(),
    setInternalNotes: vi.fn(),
    setDraftStops: vi.fn((v) => {
      state.draftStops = typeof v === "function" ? v(state.draftStops) : v;
    }),
  } satisfies ApplyLoadDocumentParseCallbacks;
}

describe("parse → manual edit → re-parse → persist", () => {
  it("keeps manually corrected rate in draft_json (not new AI extract)", async () => {
    const live = { rate: "", brokerName: "", brokerContactName: "", draftStops: [] as unknown[] };
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
    const live = { rate: "", brokerName: "", brokerContactName: "", draftStops: stops };
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
});
