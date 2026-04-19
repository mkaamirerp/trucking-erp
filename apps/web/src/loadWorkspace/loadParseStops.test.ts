import { describe, expect, it } from "vitest";
import { filterMeaningfulParsedStops, isMeaningfulParsedStop } from "./loadParseStops";
import type { LoadDocumentParseStop } from "../api";

describe("isMeaningfulParsedStop", () => {
  it("rejects blank shell with only stop_type and sequence", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0 };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });

  it("accepts facility_name", () => {
    const s: LoadDocumentParseStop = { stop_type: "pickup", sequence: 0, facility_name: "Acme DC" };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("accepts address parts only", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "delivery",
      sequence: 1,
      city: "Dallas",
      state_or_province: "TX",
    };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("accepts appointment info only", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "pickup",
      sequence: 0,
      appointment_date: "2025-01-02",
      appointment_time_text: "14:00",
    };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("accepts notes only", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "other",
      sequence: 2,
      notes: "  Gate 4  ",
    };
    expect(isMeaningfulParsedStop(s)).toBe(true);
  });

  it("rejects whitespace-only substantive fields", () => {
    const s: LoadDocumentParseStop = {
      stop_type: "pickup",
      sequence: 0,
      city: "   ",
      facility_name: "",
    };
    expect(isMeaningfulParsedStop(s)).toBe(false);
  });
});

describe("filterMeaningfulParsedStops", () => {
  it("filters mixed arrays", () => {
    const stops: LoadDocumentParseStop[] = [
      { stop_type: "pickup", sequence: 0 },
      { stop_type: "delivery", sequence: 1, city: "Austin" },
      { stop_type: "pickup", sequence: 2, reference_number: "REF-1" },
      { stop_type: "drop", sequence: 3 },
    ];
    const out = filterMeaningfulParsedStops(stops);
    expect(out).toHaveLength(2);
    expect(out[0].city).toBe("Austin");
    expect(out[1].reference_number).toBe("REF-1");
  });
});
