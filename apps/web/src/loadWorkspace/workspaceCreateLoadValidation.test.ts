import { describe, expect, it } from "vitest";
import type { Broker } from "@/api";
import { initialManualCreateStops, type WorkspaceDraftFields } from "./loadWorkspaceShared";
import { evaluateCreateLoadGate, hasLoadNumberOrPo } from "./workspaceCreateLoadValidation";

const brokers: Broker[] = [{ id: 1, name: "TQL" }];

function baseFields(overrides: Partial<WorkspaceDraftFields> = {}): WorkspaceDraftFields {
  const stops = initialManualCreateStops();
  stops[0] = { ...stops[0], city: "Toronto", state_or_province: "ON" };
  stops[1] = { ...stops[1], city: "Montreal", state_or_province: "QC" };
  return {
    status: "draft",
    loadNumber: "",
    brokerId: null,
    brokerContactId: null,
    brokerNameSnapshot: "Jaysm Logistics",
    brokerContactNameSnapshot: "",
    brokerContactPhoneSnapshot: "",
    brokerContactExtensionSnapshot: "",
    brokerContactEmailSnapshot: "",
    brokerLoadReference: "REF-100",
    loadReferences: [],
    freightMode: "",
    equipmentType: "",
    trailerType: "",
    trailerSize: "",
    commodity: "",
    estimatedWeight: "",
    hazmat: "unset",
    temperatureRequirement: "",
    palletCaseCount: "",
    rate: "",
    customerRate: "",
    miles: "",
    driverId: null,
    truckId: null,
    trailerAssetId: null,
    customsBrokerId: null,
    internalNotes: "",
    draftStops: stops,
    ...overrides,
  };
}

describe("evaluateCreateLoadGate", () => {
  it("hard-blocks without Load # / PO #", () => {
    const r = evaluateCreateLoadGate(
      baseFields({ brokerLoadReference: "", loadReferences: [] }),
      brokers,
    );
    expect(r.hardBlockMessage).toMatch(/Load # \/ PO #/);
  });

  it("accepts PO reference only for Task 2b", () => {
    expect(
      hasLoadNumberOrPo(
        baseFields({
          brokerLoadReference: "",
          loadReferences: [{ kind: "po_number", value: "4500123", label: "PO #" }],
        }),
      ),
    ).toBe(true);
  });

  it("hard-blocks without broker/carrier", () => {
    const r = evaluateCreateLoadGate(baseFields({ brokerNameSnapshot: "" }), brokers);
    expect(r.hardBlockMessage).toMatch(/Broker\/Carrier/);
  });

  it("hard-blocks without pickup city", () => {
    const stops = initialManualCreateStops();
    stops[0] = { ...stops[0], city: "", state_or_province: "ON" };
    stops[1] = { ...stops[1], city: "Montreal", state_or_province: "QC" };
    const r = evaluateCreateLoadGate(baseFields({ draftStops: stops }), brokers);
    expect(r.hardBlockMessage).toMatch(/Pickup city/);
  });

  it("passes hard gate and lists optional missing fields", () => {
    const r = evaluateCreateLoadGate(baseFields(), brokers);
    expect(r.hardBlockMessage).toBeNull();
    expect(r.missingOptionalLabels.length).toBeGreaterThan(0);
    expect(r.missingOptionalLabels).toContain("Rate");
  });
});
