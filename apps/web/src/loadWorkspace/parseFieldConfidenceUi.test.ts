import { describe, expect, it } from "vitest";
import type { LoadDocumentParseExtracted } from "@/api";
import {
  classifyParseWarningsForReview,
  computeDocumentReviewTier,
  confidenceTierForFieldKey,
  normalizeConfidenceValue,
} from "./parseFieldConfidenceUi";

const ex = (over: Partial<LoadDocumentParseExtracted> = {}): LoadDocumentParseExtracted => ({
  references: [],
  stops: [],
  ...over,
});

describe("normalizeConfidenceValue", () => {
  it("maps med to medium", () => {
    expect(normalizeConfidenceValue("med")).toBe("medium");
  });
  it("returns null for unknown", () => {
    expect(normalizeConfidenceValue("")).toBeNull();
    expect(normalizeConfidenceValue("unknown")).toBeNull();
  });
});

describe("computeDocumentReviewTier", () => {
  it("returns neutral when no confidence and no critical extract", () => {
    expect(computeDocumentReviewTier(ex(), {}, [])).toBe("neutral");
  });

  it("does not return green when critical fields are absent from extract (only rate present)", () => {
    expect(
      computeDocumentReviewTier(ex({ rate: 1200 }), { rate: "high" }, []),
    ).toBe("medium");
  });

  it("does not go green when only rate is high but broker and stops are unrated", () => {
    const tier = computeDocumentReviewTier(
      ex({
        rate: 1200,
        broker_name_snapshot: "Acme Broker",
        stops: [{ stop_type: "pickup", sequence: 0, city: "Dallas" }],
      }),
      { rate: "high" },
      [],
    );
    expect(tier).toBe("medium");
  });

  it("returns high when all in-play critical fields are high", () => {
    const tier = computeDocumentReviewTier(
      ex({
        rate: 1200,
        broker_name_snapshot: "Acme Broker",
        broker_load_reference: "BR-1",
        stops: [{ stop_type: "pickup", sequence: 0, city: "Dallas" }],
      }),
      {
        rate: "high",
        broker_name_snapshot: "high",
        broker_load_reference: "high",
        stops: "high",
      },
      [],
    );
    expect(tier).toBe("high");
  });

  it("treats non-critical warnings as review (amber), not automatic red", () => {
    const tier = computeDocumentReviewTier(
      ex({ rate: 500, broker_name_snapshot: "X", stops: [{ stop_type: "pickup", sequence: 0 }] }),
      { rate: "high", broker_name_snapshot: "high", stops: "high" },
      ["weak literal presence note"],
    );
    expect(tier).toBe("medium");
  });

  it("returns low for critical mechanical warnings", () => {
    const tier = computeDocumentReviewTier(
      ex({ rate: 500 }),
      { rate: "high" },
      ["invalid_stop_type: stops[0]"],
    );
    expect(tier).toBe("low");
  });
});

describe("classifyParseWarningsForReview", () => {
  it("flags structural stop warnings as critical", () => {
    expect(classifyParseWarningsForReview(["duplicate_stop_sequence: 0"])).toBe("critical");
  });
  it("flags generic warnings as review", () => {
    expect(classifyParseWarningsForReview(["some review note"])).toBe("review");
  });
});

describe("confidenceTierForFieldKey", () => {
  it("clears tier when manually overridden", () => {
    expect(confidenceTierForFieldKey("rate", { rate: "high" }, true)).toBeNull();
  });
});
