import { describe, expect, it } from "vitest";
import { computeLoadWorkspacePdfHydrationResult } from "./loadParseHydration";
import { createEmptyParseHydrationState } from "./loadParseHydrationState";
import type { LoadDocumentParseExtracted, LoadDocumentParseResponse } from "../api";

const baseSummary = () => ({
  resolvedBrokerId: null as number | null,
  resolvedBrokerContactId: null as number | null,
  brokerContactMatched: false,
  mcOrDotAttempted: false,
  unresolvedStopCount: 0,
  parseHydrationState: createEmptyParseHydrationState(),
  hydrationReviewNotes: [],
});

const emptyExtracted = (): LoadDocumentParseExtracted => ({
  references: [],
  stops: [],
});

const mkRes = (
  extracted: LoadDocumentParseExtracted,
  rawText: string,
  warnings: string[],
): LoadDocumentParseResponse => ({
  document: { filename: "test.pdf" },
  extracted,
  raw_text: rawText,
  warnings,
  field_confidence: {},
});

describe("computeLoadWorkspacePdfHydrationResult", () => {
  it("matches success path: warnings forwarded, toolbar success tone, labels when broker resolved", () => {
    const res = mkRes({ ...emptyExtracted(), miles: 50 }, "body", []);
    const result = computeLoadWorkspacePdfHydrationResult(res, {
      ...baseSummary(),
      resolvedBrokerId: 1,
      brokerContactMatched: true,
    });
    expect(result.warnings).toEqual([]);
    expect(result.toolbar.tone).toBe("success");
    expect(result.toolbar.text.toLowerCase()).toContain("applied");
    expect(result.appliedLabels).not.toBeNull();
  });

  it("warning tone when parse returned warnings", () => {
    const res = mkRes({ ...emptyExtracted(), commodity: "x" }, "t", ["weak pdf"]);
    const result = computeLoadWorkspacePdfHydrationResult(res, baseSummary());
    expect(result.warnings).toEqual(["weak pdf"]);
    expect(result.toolbar.tone).toBe("warning");
    expect(result.parseConfidenceTier).toBe("medium");
  });

  it("document tier is not green from a single high-confidence field", () => {
    const res = mkRes(
      {
        ...emptyExtracted(),
        rate: 900,
        broker_name_snapshot: "Broker Co",
        stops: [{ stop_type: "pickup", sequence: 0, city: "Austin" }],
      },
      "t",
      [],
    );
    res.field_confidence = { rate: "high" };
    const result = computeLoadWorkspacePdfHydrationResult(res, baseSummary());
    expect(result.parseConfidenceTier).toBe("medium");
  });

  it("appliedLabels null when no labels from builder", () => {
    const res = mkRes(emptyExtracted(), "", []);
    const result = computeLoadWorkspacePdfHydrationResult(res, baseSummary());
    expect(result.appliedLabels).toBeNull();
  });
});
