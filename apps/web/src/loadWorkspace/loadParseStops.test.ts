import { describe, expect, it } from "vitest";
import {
  filterMeaningfulParsedStops,
  hasUsefulStopIdentity,
  isMeaningfulParsedStop,
} from "./loadParseStops";
import type { LoadDocumentParseStop } from "../api";

describe("hasUsefulStopIdentity / isMeaningfulParsedStop", () => {
  it("rejects blank shell with only stop_type and sequence", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0 };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });

  it("rejects state-only fragments (2-letter noise common in regex heuristics)", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "pickup",
      sequence: 0,
      state_or_province: "OH",
    };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });

  it("rejects appointment-only without any location (no address identity)", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "pickup",
      sequence: 0,
      appointment_date: "2025-01-02",
      appointment_time_text: "14:00",
    };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });

  it("rejects very short notes (fragments, not real instructions)", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "other",
      sequence: 2,
      notes: "Gate 4",
    };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });

  it("accepts facility name with useful length", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0, facility_name: "Acme DC" };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("accepts city + state (paired)", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "delivery",
      sequence: 1,
      city: "Dallas",
      state_or_province: "TX",
    };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("accepts stand-alone city token when at least 3 characters (common RC layout)", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0, city: "Dallas" };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("accepts street with minimum length for an address line", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "pickup",
      sequence: 0,
      street: "100 Main St",
    };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("rejects over-short street", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0, street: "1 St" };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });

  it("accepts full US zip", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0, postal_code: "43215" };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("accepts reference at or above min length", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0, reference_number: "PU-1" };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("rejects 3-char reference (too short)", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0, reference_number: "X12" };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });

  it("accepts longer notes (dock / gate detail)", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "other",
      sequence: 2,
      notes: "  Check in at guard shack — Gate 4  ",
    };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("accepts appointment together with a location signal", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "pickup",
      sequence: 0,
      city: "Columbus",
      state_or_province: "OH",
      appointment_time_text: "14:00",
    };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("rejects whitespace-only values", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "pickup",
      sequence: 0,
      city: "   ",
      facility_name: "",
    };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });
});

describe("hasUsefulStopIdentity (draft alias)", () => {
  it("is exported for use on draft / save paths", () => {
    expect(
      hasUsefulStopIdentity({
        facility_name: "Shipper A",
        commodity_notes: null,
      }),
    ).toBe(true);
  });
});

describe("filterMeaningfulParsedStops", () => {
  it("keeps only rows that pass the strict gate", () => {
    const stops: LoadDocumentParseStop[] = [
      { stop_type: "pickup", sequence: 0 },
      { stop_type: "delivery", sequence: 1, city: "Austin" },
      { stop_type: "pickup", sequence: 2, reference_number: "REF-1" },
      { stop_type: "drop", sequence: 3, state_or_province: "IN" },
    ];
    const out = filterMeaningfulParsedStops(stops);
    expect(out).toHaveLength(2);
    expect(out[0].city).toBe("Austin");
    expect(out[1].reference_number).toBe("REF-1");
  });
});

/** Acceptance: parser hydration / real multi-stop (no persist — see loadWorkspaceShared.test) */
describe("Real multi-stop & noisy parser (filterMeaningfulParsedStops + isMeaningfulParsedStop)", () => {
  it("2. Eleven noisy parser-style shells (e.g. state-only): no rows survive the filter", () => {
    const noise: LoadDocumentParseStop[] = Array.from({ length: 11 }, (_, i) => ({
      stop_type: "pickup" as const,
      sequence: i,
      state_or_province: "IN",
    }));
    expect(filterMeaningfulParsedStops(noise)).toHaveLength(0);
  });

  it("3. Multi-stop (2× PICKUP + 1× DEL): all 3 with facility/city survive the parse filter", () => {
    const stops: LoadDocumentParseStop[] = [
      { stop_type: "pickup", sequence: 0, facility_name: "DC West", city: "OKC" },
      { stop_type: "pickup", sequence: 1, facility_name: "Transload" },
      { stop_type: "delivery", sequence: 2, city: "Dallas" },
    ];
    const out = filterMeaningfulParsedStops(stops);
    expect(out).toHaveLength(3);
    expect(out.map((s) => s.city ?? s.facility_name)).toEqual([
      "OKC",
      "Transload",
      "Dallas",
    ]);
  });

  it("4. Multi-drop (1× PICK + 2× DEL): all 3 with facility/city survive the parse filter", () => {
    const stops: LoadDocumentParseStop[] = [
      { stop_type: "pickup", sequence: 0, city: "Laredo" },
      { stop_type: "delivery", sequence: 1, facility_name: "Yard A" },
      { stop_type: "drop", sequence: 2, city: "Houston" },
    ];
    const out = filterMeaningfulParsedStops(stops);
    expect(out).toHaveLength(3);
  });

  it("5. Appointment-only stop (no facility/street/city) is dropped from the parse filter", () => {
    const stops: LoadDocumentParseStop[] = [
      { stop_type: "pickup", sequence: 0, city: "Dallas" },
      {
        stop_type: "pickup",
        sequence: 1,
        appointment_date: "2026-04-26",
        appointment_time_text: "08:00",
      },
      { stop_type: "delivery", sequence: 2, city: "Austin" },
    ];
    const out = filterMeaningfulParsedStops(stops);
    expect(out).toHaveLength(2);
    expect(out[0].city).toBe("Dallas");
    expect(out[1].city).toBe("Austin");
  });

  it("6. Reference-only: short junk ref dropped; ref length >= MIN_REF (4) survives (current rule)", () => {
    expect(isMeaningfulParsedStop({ stop_type: "pickup", sequence: 0, reference_number: "AB" })).toBe(
      false,
    );
    expect(isMeaningfulParsedStop({ stop_type: "pickup", sequence: 0, reference_number: "X12" })).toBe(false);
    expect(isMeaningfulParsedStop({ stop_type: "pickup", sequence: 0, reference_number: "X123" })).toBe(
      true,
    );
    expect(
      isMeaningfulParsedStop({ stop_type: "pickup", sequence: 0, reference_number: "PU-1" }),
    ).toBe(true);
  });
});
