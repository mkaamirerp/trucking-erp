/**
 * Issue 0A — frontend Load writer freeze.
 * Save carries commercial fields only; create is draft-only; the legacy Load assignment strip is gone.
 */
import { describe, expect, it } from "vitest";
import type { Load } from "@/api";
import { OPS } from "@/routes";
import {
  baselineSignatureFromLoad,
  buildLoadCreatePayload,
  buildLoadPersistPayload,
  buildLoadPersistPayloadFromWorkspaceFields,
  initialManualCreateStops,
  workspaceFieldsFromLoad,
  type LoadPersistParams,
} from "./loadWorkspaceShared";

const SOURCES = import.meta.glob<string>(
  [
    "../pages/LoadWorkspacePage.tsx",
    "../pages/DeprecatedDispatchPage.tsx",
    "./LoadWorkspaceForm.tsx",
    "./DispatchAssignmentStrip.tsx",
  ],
  { query: "?raw", import: "default", eager: true },
);

function source(path: string): string {
  const text = SOURCES[path];
  expect(text, path).toBeTypeOf("string");
  return text;
}

const OPERATIONAL_KEYS = ["status", "driver_id", "truck_id", "trailer_id"] as const;
const ASSIGNMENT_KEYS = ["driver_id", "truck_id", "trailer_id"] as const;

function params(over: Partial<LoadPersistParams> = {}): LoadPersistParams {
  return {
    loadNumber: "L-1",
    brokerId: null,
    brokerContactId: null,
    brokerNameSnapshot: "Broker",
    brokerContactNameSnapshot: "",
    brokerContactPhoneSnapshot: "",
    brokerContactExtensionSnapshot: "",
    brokerContactEmailSnapshot: "",
    brokerLoadReference: "REF-1",
    loadReferences: [],
    mode: "",
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
    customsBrokerId: null,
    internalNotes: "",
    draftStops: initialManualCreateStops(),
    ...over,
  };
}

/** Historical legacy row: operational status, Load equipment, and dispatch-trip pointers set. */
function legacyDispatchedLoad(): Load {
  return {
    id: 77,
    load_number: "HIST-77",
    status: "dispatched",
    concurrency_version: 4,
    driver_id: 11,
    truck_id: 12,
    trailer_id: 13,
    trip_number: "IKL10042",
    active_dispatch_trip_id: 501,
    active_trip_id: 601,
    broker_name_snapshot: "Legacy Broker",
    broker_load_reference: "OLD-REF",
    internal_notes: "old note",
    stops: [],
  } as unknown as Load;
}

describe("Issue 0A — Save payload", () => {
  it("19. normal Save omits status", () => {
    const body = buildLoadPersistPayload(params()) as Record<string, unknown>;
    expect(body).not.toHaveProperty("status");
  });

  it("20. normal Save omits driver_id / truck_id / trailer_id", () => {
    const body = buildLoadPersistPayload(params()) as Record<string, unknown>;
    for (const k of ASSIGNMENT_KEYS) expect(body).not.toHaveProperty(k);
  });

  it("22. historical legacy Load: commercial edit payload carries the edit and no operational fields", () => {
    const fields = workspaceFieldsFromLoad(legacyDispatchedLoad());
    expect(fields.status).toBe("dispatched");
    expect(fields.driverId).toBe(11);
    const body = buildLoadPersistPayloadFromWorkspaceFields({
      ...fields,
      internalNotes: "new commercial note",
      brokerLoadReference: "NEW-REF",
    }) as Record<string, unknown>;
    expect(body.internal_notes).toBe("new commercial note");
    expect(body.broker_load_reference).toBe("NEW-REF");
    for (const k of OPERATIONAL_KEYS) expect(body).not.toHaveProperty(k);
  });

  it("22b. baseline signature for a legacy row ignores status and Load equipment", () => {
    const base = legacyDispatchedLoad();
    const sig = baselineSignatureFromLoad(base);
    for (const k of OPERATIONAL_KEYS) expect(sig).not.toContain(`"${k}"`);
    expect(baselineSignatureFromLoad({ ...base, status: "ready", driver_id: null } as Load)).toBe(sig);
  });
});

describe("Issue 0A — create payload", () => {
  it("23. create submits status=draft and no Load equipment", () => {
    const body = buildLoadCreatePayload(params()) as Record<string, unknown>;
    expect(body.status).toBe("draft");
    for (const k of ASSIGNMENT_KEYS) expect(body).not.toHaveProperty(k);
  });
});

describe("Issue 0A — legacy assignment UI unreachable", () => {
  it("21. DispatchAssignmentStrip and ?dispatchAssign=1 are removed", () => {
    expect(SOURCES).not.toHaveProperty("./DispatchAssignmentStrip.tsx");
    expect(OPS).not.toHaveProperty("LOAD_DISPATCH_ASSIGN_QUERY");

    const page = source("../pages/LoadWorkspacePage.tsx");
    expect(page).not.toMatch(/DispatchAssignmentStrip|dispatchAssign|onDispatchAssign/);
    expect(page).not.toMatch(/status:\s*"assigned"/);
    expect(page).not.toMatch(/driver_id:\s*driverId/);

    const board = source("../pages/DeprecatedDispatchPage.tsx");
    expect(board).not.toMatch(/dispatchAssign|LOAD_DISPATCH_ASSIGN_QUERY/);
  });

  it("21b. Load form renders status and assignment as read-only (no setters, no selects)", () => {
    const form = source("./LoadWorkspaceForm.tsx");
    expect(form).not.toMatch(/setStatus|setDriverId|setTruckId|setTrailerAssetId|LOAD_STATUSES/);
    expect(form).toContain('data-testid="load-status-readonly"');
    expect(form).toContain('data-testid="load-driver-readonly"');
  });
});
