import { describe, expect, it } from "vitest";
import type { Broker } from "@/api";
import { initialManualCreateStops, type WorkspaceDraftFields } from "./loadWorkspaceShared";
import { createEmptyParseHydrationState } from "./loadParseHydrationState";
import {
  BROKER_LOAD_NUMBER_PO_LABEL,
  draftHasParsedPdf,
  evaluateCreateLoadGate,
  formatSoftNotProvidedLine,
  hasBrokerLoadNumberOrPo,
  listManualCreateHardMissing,
  listCreateLoadSoftNotProvided,
} from "./workspaceCreateLoadValidation";

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
  it("manual hard-blocks without pickup city", () => {
    const stops = initialManualCreateStops();
    stops[0] = { ...stops[0], city: "", state_or_province: "ON" };
    stops[1] = { ...stops[1], city: "Montreal", state_or_province: "QC" };
    const r = evaluateCreateLoadGate(baseFields({ draftStops: stops }), brokers);
    expect(r.hardBlockMessage).toMatch(/Pickup city/);
  });

  it("manual hard gate does not require broker", () => {
    const missing = listManualCreateHardMissing(
      baseFields({ brokerNameSnapshot: "", brokerLoadReference: "" }),
    );
    expect(missing).toEqual([]);
  });

  it("passes manual hard gate with pickup and delivery city/state", () => {
    const r = evaluateCreateLoadGate(baseFields(), brokers);
    expect(r.hardBlockMessage).toBeNull();
    expect(r.missingOptionalLabels.length).toBeGreaterThan(0);
  });
});

describe("parsed create soft notes", () => {
  it("draftHasParsedPdf when accepted_parse_json present", () => {
    expect(
      draftHasParsedPdf(
        {
          id: "x",
          accepted_parse_json: { extracted: {} },
          pdf_filename: null,
          status: "draft",
          concurrency_version: 1,
          draft_json: {},
          created_at: "",
          updated_at: "",
        },
        createEmptyParseHydrationState(),
      ),
    ).toBe(true);
  });

  it("soft note lists broker load # / PO # when missing", () => {
    const line = formatSoftNotProvidedLine(
      listCreateLoadSoftNotProvided(
        baseFields({ brokerLoadReference: "", loadReferences: [] }),
        brokers,
      ),
    );
    expect(line).toMatch(/^Not provided:/);
    expect(line).toContain(BROKER_LOAD_NUMBER_PO_LABEL);
  });

  it("hasBrokerLoadNumberOrPo requires brokerLoadReference only", () => {
    expect(
      hasBrokerLoadNumberOrPo(
        baseFields({
          brokerLoadReference: "",
          loadReferences: [{ kind: "po_number", value: "4500123", label: "PO #" }],
        }),
      ),
    ).toBe(false);
    expect(hasBrokerLoadNumberOrPo(baseFields({ brokerLoadReference: "REF-9" }))).toBe(true);
  });
});
