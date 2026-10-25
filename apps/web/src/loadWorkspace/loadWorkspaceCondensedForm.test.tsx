import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { LoadWorkspaceCondensedForm } from "./LoadWorkspaceCondensedForm";
import {
  buildLoadPersistPayloadFromWorkspaceFields,
  initialManualCreateStops,
  type WorkspaceDraftFields,
} from "./loadWorkspaceShared";

function minimalCondensedProps() {
  const stops = initialManualCreateStops().map((s, i) => ({
    ...s,
    notes: i === 0 ? "Call dock" : "",
    commodity_notes: i === 0 ? "Keep frozen" : "",
  }));
  return {
    mode: "manual" as const,
    intakeProposed: null,
    saving: false,
    freightBrokers: [],
    brokerContacts: [],
    drivers: [],
    trucks: [],
    trailers: [],
    customsBrokers: [],
    customsMessage: null,
    customsBrokerLocked: false,
    onCustomsBrokerChange: vi.fn(),
    showOperationalNotesTimeline: false,
    loadNotes: [],
    newNoteBody: "",
    setNewNoteBody: vi.fn(),
    onAddNote: vi.fn(),
    focusDoc: vi.fn(),
    verificationTabIndex: new Map<string, number>(),
    status: "draft",
    loadNumber: "",
    setLoadNumber: vi.fn(),
    brokerId: null,
    setBrokerId: vi.fn(),
    brokerContactId: null,
    setBrokerContactId: vi.fn(),
    brokerNameSnapshot: "",
    setBrokerNameSnapshot: vi.fn(),
    brokerContactNameSnapshot: "",
    setBrokerContactNameSnapshot: vi.fn(),
    brokerContactPhoneSnapshot: "",
    setBrokerContactPhoneSnapshot: vi.fn(),
    brokerContactExtensionSnapshot: "",
    setBrokerContactExtensionSnapshot: vi.fn(),
    brokerContactEmailSnapshot: "",
    setBrokerContactEmailSnapshot: vi.fn(),
    brokerLoadReference: "",
    setBrokerLoadReference: vi.fn(),
    loadReferences: [],
    freightMode: "",
    setFreightMode: vi.fn(),
    equipmentType: "",
    setEquipmentType: vi.fn(),
    trailerType: "",
    setTrailerType: vi.fn(),
    trailerSize: "",
    setTrailerSize: vi.fn(),
    commodity: "",
    setCommodity: vi.fn(),
    estimatedWeight: "",
    setEstimatedWeight: vi.fn(),
    hazmat: "unset" as const,
    setHazmat: vi.fn(),
    temperatureRequirement: "",
    setTemperatureRequirement: vi.fn(),
    palletCaseCount: "",
    setPalletCaseCount: vi.fn(),
    rate: "1800",
    setRate: vi.fn(),
    customerRate: "",
    setCustomerRate: vi.fn(),
    miles: "",
    setMiles: vi.fn(),
    driverId: null,
    truckId: null,
    trailerAssetId: null,
    customsBrokerId: null,
    internalNotes: "",
    setInternalNotes: vi.fn(),
    draftStops: stops,
    sortedDraftStops: stops,
    updateStop: vi.fn(),
    removeStop: vi.fn(),
    addStop: vi.fn(),
    moveStop: vi.fn(),
    workspaceHasRateConfirmationPdf: true,
    renderNotes: true,
    operatorStatusInput: { status: "draft" },
  };
}

describe("LoadWorkspaceCondensedForm", () => {
  it("renders stop notes and commodity notes fields in markup", () => {
    const html = renderToStaticMarkup(<LoadWorkspaceCondensedForm {...minimalCondensedProps()} />);
    expect(html).toContain('data-testid="stop-notes-input"');
    expect(html).toContain('data-testid="commodity-notes-input"');
    expect(html).toContain("Call dock");
    expect(html).toContain("Keep frozen");
  });

  it("includes stop notes in persist payload when saved", () => {
    const stops = initialManualCreateStops();
    stops[0] = { ...stops[0], notes: "Dock 4", commodity_notes: "No stack" };
    const fields: WorkspaceDraftFields = {
      loadNumber: "",
      brokerId: null,
      brokerContactId: null,
      brokerNameSnapshot: "B",
      brokerContactNameSnapshot: "",
      brokerContactPhoneSnapshot: "",
      brokerContactExtensionSnapshot: "",
      brokerContactEmailSnapshot: "",
      brokerLoadReference: "REF",
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
      rate: "100",
      customerRate: "",
      miles: "",
      customsBrokerId: null,
      internalNotes: "",
      draftStops: stops,
    };
    const payload = buildLoadPersistPayloadFromWorkspaceFields(fields);
    expect(payload.stops?.[0]?.notes).toBe("Dock 4");
    expect(payload.stops?.[0]?.commodity_notes).toBe("No stack");
  });
});
