import { describe, expect, it, vi } from "vitest";
import { applyLoadDocumentParseResponse } from "./applyLoadDocumentParseResponse";
import type { LoadDocumentParseResponse } from "@/api";

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
});
