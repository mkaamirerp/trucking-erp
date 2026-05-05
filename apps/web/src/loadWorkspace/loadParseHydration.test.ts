import { describe, expect, it } from "vitest";
import { computeLoadWorkspacePdfHydrationResult } from "./loadParseHydration";
import type { LoadDocumentParseExtracted, LoadDocumentParseResponse } from "../api";

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
      resolvedBrokerId: 1,
      brokerContactMatched: true,
      mcOrDotAttempted: false,
    });
    expect(result.warnings).toEqual([]);
    expect(result.toolbar.tone).toBe("success");
    expect(result.toolbar.text.toLowerCase()).toContain("applied");
    expect(result.appliedLabels).not.toBeNull();
  });

  it("warning tone when parse returned warnings", () => {
    const res = mkRes({ ...emptyExtracted(), commodity: "x" }, "t", ["weak pdf"]);
    const result = computeLoadWorkspacePdfHydrationResult(res, {
      resolvedBrokerId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
    });
    expect(result.warnings).toEqual(["weak pdf"]);
    expect(result.toolbar.tone).toBe("warning");
  });

  it("appliedLabels null when no labels from builder", () => {
    const res = mkRes(emptyExtracted(), "", []);
    const result = computeLoadWorkspacePdfHydrationResult(res, {
      resolvedBrokerId: null,
      brokerContactMatched: false,
      mcOrDotAttempted: false,
    });
    expect(result.appliedLabels).toBeNull();
  });
});
