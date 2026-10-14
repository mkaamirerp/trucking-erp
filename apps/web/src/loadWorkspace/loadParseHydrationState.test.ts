import { describe, expect, it, vi } from "vitest";
import {
  applyParseScalarHydration,
  createEmptyParseHydrationState,
  registerManualParseFieldEdit,
} from "./loadParseHydrationState";
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
});
