import { describe, expect, it, vi } from "vitest";
import {
  applyParseScalarHydration,
  createEmptyParseHydrationState,
  hydrationStateFromDraftAndParse,
  inferParseManualOverridesFromDraft,
  markBrokerIdentityLocked,
  markOperatorEditedParseScalar,
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

  it("does not overwrite broker name when broker identity is locked", () => {
    const cbs = mkCbs();
    let state = createEmptyParseHydrationState();
    state = applyParseScalarHydration({ broker_name_snapshot: "Broker A" } as never, cbs, state);
    markBrokerIdentityLocked(state);
    vi.mocked(cbs.setBrokerNameSnapshot).mockClear();
    state = applyParseScalarHydration({ broker_name_snapshot: "Broker B" } as never, cbs, state);
    expect(cbs.setBrokerNameSnapshot).not.toHaveBeenCalledWith("Broker B");
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

  it("hydrates customer rate from RC rate when parser omits customer_rate", () => {
    const cbs = mkCbs();
    let state = createEmptyParseHydrationState();
    state = applyParseScalarHydration({ rate: 2500 } as never, cbs, state);
    expect(cbs.setCustomerRate).toHaveBeenCalledWith("");
    expect(state.lastAppliedValues.get("customerRate")).toBe("2500");
  });

  it("follows RC rate on re-parse when customer mirrors rate", () => {
    const cbs = mkCbs();
    let state = createEmptyParseHydrationState();
    state = applyParseScalarHydration({ rate: 1000 } as never, cbs, state);
    vi.mocked(cbs.setCustomerRate).mockClear();
    state = applyParseScalarHydration({ rate: 900 } as never, cbs, state);
    expect(cbs.setCustomerRate).toHaveBeenCalledWith("");
    expect(state.lastAppliedValues.get("customerRate")).toBe("900");
  });

  it("does not overwrite manually edited customer rate on re-parse", () => {
    const cbs = mkCbs();
    let state = createEmptyParseHydrationState();
    state = applyParseScalarHydration({ rate: 1000 } as never, cbs, state);
    markOperatorEditedParseScalar(state, "customerRate");
    vi.mocked(cbs.setCustomerRate).mockClear();
    state = applyParseScalarHydration({ rate: 800 } as never, cbs, state);
    expect(cbs.setCustomerRate).not.toHaveBeenCalled();
    expect(state.manualOverrideKeys.has("customerRate")).toBe(true);
  });

  it("parsed customer stays parser-owned until operator edits", () => {
    const cbs = mkCbs();
    let state = createEmptyParseHydrationState();
    state = applyParseScalarHydration({ rate: 2000, customer_rate: 1500 } as never, cbs, state);
    expect(cbs.setCustomerRate).toHaveBeenCalledWith("1500");
    vi.mocked(cbs.setCustomerRate).mockClear();
    state = applyParseScalarHydration({ rate: 2000, customer_rate: 1400 } as never, cbs, state);
    expect(cbs.setCustomerRate).toHaveBeenCalledWith("1400");
    expect(state.manualOverrideKeys.has("customerRate")).toBe(false);
  });

  it("operator-entered customer matching RC is protected when persisted on reopen", () => {
    const ex = { rate: 2000 } as never;
    const fields = { ...initialWorkspaceFieldsManual(), rate: "2000", customerRate: "2000" };
    const persisted = new Set(["customerRate" as const]);
    const state = hydrationStateFromDraftAndParse(fields, ex, persisted);
    expect(state.manualOverrideKeys.has("customerRate")).toBe(true);
  });

  it("reopen uses persisted keys not customer-vs-rate heuristic", () => {
    const ex = { rate: 2000 } as never;
    const fields = { ...initialWorkspaceFieldsManual(), rate: "2000", customerRate: "2000" };
    expect(inferParseManualOverridesFromDraft(fields, ex).has("customerRate")).toBe(false);
    expect(
      inferParseManualOverridesFromDraft(fields, ex, new Set(["customerRate"])).has("customerRate"),
    ).toBe(true);
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
