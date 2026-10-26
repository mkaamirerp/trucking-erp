import { describe, expect, it } from "vitest";
import {
  confidenceTierForAppliedLabel,
  worstParseConfidenceTier,
} from "./parseFieldConfidenceUi";

describe("worstParseConfidenceTier", () => {
  it("returns low when parse warnings exist", () => {
    expect(worstParseConfidenceTier({ rate: "high" }, ["note"])).toBe("low");
  });

  it("returns lowest tier among field_confidence values", () => {
    expect(
      worstParseConfidenceTier({
        broker_name_snapshot: "high",
        rate: "low",
        miles: "medium",
      }),
    ).toBe("low");
  });

  it("defaults to medium when no confidence map", () => {
    expect(worstParseConfidenceTier({}, [])).toBe("medium");
  });
});

describe("confidenceTierForAppliedLabel", () => {
  it("maps broker load reference label to broker_load_reference confidence", () => {
    expect(
      confidenceTierForAppliedLabel("Load Number", { broker_load_reference: "low" }),
    ).toBe("low");
  });
});
