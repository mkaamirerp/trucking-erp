import { describe, expect, it } from "vitest";
import {
  buildLoadPersistPayload,
  initialManualCreateStops,
  newDraftStop,
  selectDraftStopsForPersist,
} from "./loadWorkspaceShared";
import type { DraftStop } from "./loadWorkspaceShared";

function minimalPersist(over: Partial<Parameters<typeof buildLoadPersistPayload>[0]> = {}) {
  return {
    status: "unassigned",
    loadNumber: "",
    brokerId: null,
    brokerContactId: null,
    brokerNameSnapshot: "",
    brokerContactNameSnapshot: "",
    brokerContactPhoneSnapshot: "",
    brokerContactExtensionSnapshot: "",
    brokerContactEmailSnapshot: "",
    brokerLoadReference: "",
    loadReferences: [],
    mode: "",
    equipmentType: "",
    trailerType: "",
    trailerSize: "",
    commodity: "",
    estimatedWeight: "",
    hazmat: "unset" as const,
    temperatureRequirement: "",
    palletCaseCount: "",
    rate: "",
    customerRate: "",
    miles: "",
    driverId: null,
    truckId: null,
    trailerId: null,
    customsBrokerId: null,
    internalNotes: "",
    draftStops: initialManualCreateStops(),
    ...over,
  };
}

describe("selectDraftStopsForPersist", () => {
  it("1. Manual blank PICKUP + DELIVERY: 2 rows survive selection", () => {
    const d = initialManualCreateStops();
    expect(d).toHaveLength(2);
    const out = selectDraftStopsForPersist(d);
    expect(out).toHaveLength(2);
  });

  it("2. Eleven noisy parser-style empty rows: none survive (no PICK+DEL lead pair)", () => {
    const noise: DraftStop[] = Array.from({ length: 11 }, (_, i) => newDraftStop(i, "PICKUP"));
    expect(selectDraftStopsForPersist(noise)).toHaveLength(0);
  });

  it("After manual PICK+DEL pair, extra blank PICK/DROP rows are not kept", () => {
    const rows: DraftStop[] = [
      ...initialManualCreateStops(),
      newDraftStop(2, "PICKUP"),
      newDraftStop(3, "DROP"),
    ];
    const out = selectDraftStopsForPersist(rows);
    expect(out).toHaveLength(2);
    expect((out[0].stop_type || "").toUpperCase()).toBe("PICKUP");
  });

  it("3. Multi-stop (2× PICKUP + 1× DEL) with facility/city: all 3 survive selection", () => {
    const s0: DraftStop = { ...newDraftStop(0, "PICKUP"), facility_name: "DC West", city: "OKC" };
    const s1: DraftStop = { ...newDraftStop(1, "PICKUP"), facility_name: "Transload" };
    const s2: DraftStop = { ...newDraftStop(2, "DELIVERY"), city: "Dallas" };
    const out = selectDraftStopsForPersist([s0, s1, s2]);
    expect(out).toHaveLength(3);
    expect(out[0].facility_name).toBe("DC West");
    expect(out[1].facility_name).toBe("Transload");
    expect(out[2].city).toBe("Dallas");
  });

  it("4. Multi-drop (1× PICK + 2× DEL/DROP) with city/facility: all 3 survive selection", () => {
    const a: DraftStop = { ...newDraftStop(0, "PICKUP"), city: "Laredo" };
    const b: DraftStop = { ...newDraftStop(1, "DELIVERY"), facility_name: "Yard A" };
    const c: DraftStop = { ...newDraftStop(2, "DROP"), city: "Houston" };
    const out = selectDraftStopsForPersist([a, b, c]);
    expect(out).toHaveLength(3);
  });

  it("5. Appointment-only row is dropped (leading PICK+DEL kept; appt shell not index 0/1 as pair rescue)", () => {
    const r0 = newDraftStop(0, "PICKUP");
    const r1 = newDraftStop(1, "DELIVERY");
    const r2: DraftStop = {
      ...newDraftStop(2, "PICKUP"),
      appointment_date: "2026-04-27",
      appointment_time_text: "10:00",
    };
    const r3: DraftStop = { ...newDraftStop(3, "DELIVERY"), city: "Austin" };
    const out = selectDraftStopsForPersist([r0, r1, r2, r3]);
    expect(out).toHaveLength(3);
    expect((out[2] as DraftStop).city).toBe("Austin");
    expect(
      out.some((r) => (r.appointment_date ?? "") !== "" && !(r.city ?? "").length),
    ).toBe(false);
  });

  it("6. Short junk ref on a non-pair row is dropped; ref length >= 4 survives (current rule)", () => {
    const a = { ...newDraftStop(0, "PICKUP"), city: "Dallas" };
    const b = { ...newDraftStop(1, "DELIVERY"), city: "Houston" };
    const junkRef = { ...newDraftStop(2, "PICKUP"), reference_number: "ab" } as DraftStop;
    const goodRef = { ...newDraftStop(3, "DELIVERY"), reference_number: "PU-1" } as DraftStop;
    const out = selectDraftStopsForPersist([a, b, junkRef, goodRef]);
    expect(out).toHaveLength(3);
    expect(out.map((r) => r.reference_number).filter((x) => (x ?? "").length > 0)).toEqual([
      "PU-1",
    ]);
  });
});

describe("buildLoadPersistPayload (stop safety)", () => {
  it("1. Manual blank PICKUP + DELIVERY: save payload has exactly 2 stops", () => {
    const p = buildLoadPersistPayload(
      minimalPersist({ draftStops: initialManualCreateStops() }),
    );
    expect(p.stops).toBeDefined();
    expect(p.stops?.length).toBe(2);
  });

  it("2. Eleven noisy empty rows: save payload has no stops (no weak shells persisted)", () => {
    const noise: DraftStop[] = Array.from({ length: 11 }, (_, i) => newDraftStop(i, "PICKUP"));
    const p = buildLoadPersistPayload(minimalPersist({ draftStops: noise }));
    expect(p.stops?.length).toBe(0);
  });

  it("3. Multi-stop (2× PICK + 1× DEL) with facility/city: all 3 in save payload", () => {
    const s0: DraftStop = { ...newDraftStop(0, "PICKUP"), facility_name: "DC West", city: "OKC" };
    const s1: DraftStop = { ...newDraftStop(1, "PICKUP"), facility_name: "Transload" };
    const s2: DraftStop = { ...newDraftStop(2, "DELIVERY"), city: "Dallas" };
    const p = buildLoadPersistPayload(minimalPersist({ draftStops: [s0, s1, s2] }));
    expect(p.stops?.length).toBe(3);
    expect(p.stops?.[0].facility_name).toBe("DC West");
    expect(p.stops?.[2].city).toBe("Dallas");
  });

  it("4. Multi-drop (1× PICK + 2× DEL) with city/facility: all 3 in save payload", () => {
    const a: DraftStop = { ...newDraftStop(0, "PICKUP"), city: "Laredo" };
    const b: DraftStop = { ...newDraftStop(1, "DELIVERY"), facility_name: "Yard A" };
    const c: DraftStop = { ...newDraftStop(2, "DROP"), city: "Houston" };
    const p = buildLoadPersistPayload(minimalPersist({ draftStops: [a, b, c] }));
    expect(p.stops?.length).toBe(3);
  });

  it("5. Appointment-only middle stop is omitted from save payload (PICK+DEL lead + appt shell + final DEL)", () => {
    const r0 = newDraftStop(0, "PICKUP");
    const r1 = newDraftStop(1, "DELIVERY");
    const r2: DraftStop = {
      ...newDraftStop(2, "PICKUP"),
      appointment_date: "2026-04-27",
      appointment_time_text: "10:00",
    };
    const r3: DraftStop = { ...newDraftStop(3, "DELIVERY"), city: "Austin" };
    const p = buildLoadPersistPayload(minimalPersist({ draftStops: [r0, r1, r2, r3] }));
    expect(p.stops?.length).toBe(3);
    const hasNakedAppt = p.stops?.some(
      (s) => (s.appointment_date || s.appointment_time_text) && !(s.city ?? "").length,
    );
    expect(hasNakedAppt).toBe(false);
  });

  it("6. Save payload keeps ref >= 4 on extra stops; short junk ref row dropped", () => {
    const a = { ...newDraftStop(0, "PICKUP"), city: "Dallas" };
    const b = { ...newDraftStop(1, "DELIVERY"), city: "Houston" };
    const junkRef = { ...newDraftStop(2, "PICKUP"), reference_number: "ab" } as DraftStop;
    const goodRef = { ...newDraftStop(3, "DELIVERY"), reference_number: "PU-1" } as DraftStop;
    const p = buildLoadPersistPayload(minimalPersist({ draftStops: [a, b, junkRef, goodRef] }));
    expect(p.stops?.length).toBe(3);
    const refs = p.stops?.map((s) => s.reference_number).filter((x) => (x ?? "").length > 0) ?? [];
    expect(refs).toEqual(["PU-1"]);
  });

  it("keeps the leading PICKUP+DEL pair and drops only noise PICK rows beyond (Memphis on DEL)", () => {
    const a = newDraftStop(0, "PICKUP");
    const b = { ...newDraftStop(1, "DELIVERY"), city: "Memphis" };
    const others: DraftStop[] = Array.from({ length: 4 }, (_, i) => newDraftStop(i + 2, "PICKUP"));
    const p = buildLoadPersistPayload(
      minimalPersist({ draftStops: [a, b, ...others] }),
    );
    expect(p.stops?.length).toBe(2);
    expect(p.stops?.[0].stop_type).toBe("PICKUP");
    expect(p.stops?.[1].stop_type).toBe("DELIVERY");
    expect(p.stops?.[1].city).toBe("Memphis");
  });

  it("save payload includes load-level references", () => {
    const p = buildLoadPersistPayload(
      minimalPersist({
        loadReferences: [
          { kind: "po_number", value: "PO-1", label: "PO #" },
          { kind: "bol_number", value: "BOL-9" },
        ],
      }),
    );
    expect(p.references).toEqual([
      { kind: "po_number", value: "PO-1", label: "PO #" },
      { kind: "bol_number", value: "BOL-9" },
    ]);
  });
});
