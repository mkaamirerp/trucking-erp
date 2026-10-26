import { describe, expect, it, vi } from "vitest";
import {
  applyParseScalarHydration,
  createEmptyParseHydrationState,
  hydrationStateFromDraftAndParse,
  inferParseManualOverridesFromDraft,
  registerManualParseFieldEdit,
} from "./loadParseHydrationState";
import { initialWorkspaceFieldsManual } from "./loadWorkspaceShared";
import type { ApplyLoadDocumentParseCallbacks } from "./applyLoadDocumentParseResponse";

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

describe("loadParseHydrationState", () => {
  it("clears stale parse-owned scalar when next document omits it", () => {
    const cbs = mkCbs();
    let state = createEmptyParseHydrationState();
    state = applyParseScalarHydration({ commodity: "A" } as never, cbs, state);
    expect(cbs.setCommodity).toHaveBeenCalledWith("A");
    vi.mocked(cbs.setCommodity).mockClear();
    state = applyParseScalarHydration({} as never, cbs, state);
    expect(cbs.setCommodity).toHaveBeenCalledWith("");
  });

  it("keeps manual override when next document omits field", () => {
    const cbs = mkCbs();
    let state = createEmptyParseHydrationState();
    state = applyParseScalarHydration({ commodity: "A" } as never, cbs, state);
    registerManualParseFieldEdit(state, "commodity", "Operator edit");
    vi.mocked(cbs.setCommodity).mockClear();
    state = applyParseScalarHydration({} as never, cbs, state);
    expect(cbs.setCommodity).not.toHaveBeenCalled();
  });

  it("reopen preserves broker/contact pair when both saved on draft", () => {
    const fields = {
      ...initialWorkspaceFieldsManual(),
      brokerId: 99,
      brokerNameSnapshot: "Acme Freight",
      brokerContactId: 10,
    };
    const ex = {
      broker_name_snapshot: "Acme Freight",
      broker_mc_number_snapshot: "123",
      broker_contact_name_snapshot: "Sam",
    } as never;
    const state = hydrationStateFromDraftAndParse(fields, ex);
    expect(state.brokerIdentityLocked).toBe(true);
    expect(state.brokerContactIdManuallySelected).toBe(true);
  });

  it("locks broker identity on reopen when draft broker id differs from MC/DOT re-resolution", () => {
    const fields = {
      ...initialWorkspaceFieldsManual(),
      brokerId: 99,
      brokerNameSnapshot: "Acme Freight",
    };
    const ex = {
      broker_name_snapshot: "Acme Freight",
      broker_mc_number_snapshot: "123",
    } as never;
    const state = hydrationStateFromDraftAndParse(fields, ex);
    expect(state.brokerIdentityLocked).toBe(true);
    expect(state.brokerContactIdManuallySelected).toBe(false);
  });

  it("infers manual overrides when draft value differs from accepted parse", () => {
    const fields = {
      ...initialWorkspaceFieldsManual(),
      rate: "1500",
      commodity: "Steel",
    };
    const ex = { rate: 1200, commodity: "Steel" } as never;
    const overrides = inferParseManualOverridesFromDraft(fields, ex);
    expect(overrides.has("rate")).toBe(true);
    expect(overrides.has("commodity")).toBe(false);
    const state = hydrationStateFromDraftAndParse(fields, ex);
    expect(state.manualOverrideKeys.has("rate")).toBe(true);
  });
});
