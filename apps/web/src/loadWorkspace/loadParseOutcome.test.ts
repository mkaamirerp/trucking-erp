import { describe, expect, it } from "vitest";
import { countMeaningfulExtractedFields, describeWorkspacePdfParseOutcome } from "./loadParseOutcome";
import type { LoadDocumentParseExtracted } from "../api";

const emptyExtracted = (): LoadDocumentParseExtracted => ({
  references: [],
  stops: [],
});

describe("countMeaningfulExtractedFields", () => {
  it("counts non-empty snapshots and structured slices", () => {
    const ex: LoadDocumentParseExtracted = {
      ...emptyExtracted(),
      broker_mc_number_snapshot: " 123456 ",
      rate: 100,
      stops: [{ stop_type: "pickup", sequence: 0 }],
    };
    expect(countMeaningfulExtractedFields(ex)).toBe(3);
  });

  it("returns 0 for empty extracted", () => {
    expect(countMeaningfulExtractedFields(emptyExtracted())).toBe(0);
  });
});

describe("describeWorkspacePdfParseOutcome", () => {
  it("success when fields applied and no warnings", () => {
    const ex: LoadDocumentParseExtracted = { ...emptyExtracted(), miles: 100 };
    const o = describeWorkspacePdfParseOutcome(ex, "some text", []);
    expect(o.tone).toBe("success");
    expect(o.headline.toLowerCase()).toContain("applied");
  });

  it("warning when fields and warnings", () => {
    const ex: LoadDocumentParseExtracted = { ...emptyExtracted(), commodity: "Steel" };
    const o = describeWorkspacePdfParseOutcome(ex, "x", ["pypdf not installed"]);
    expect(o.tone).toBe("warning");
    expect(o.headline.toLowerCase()).toContain("parse notes");
  });

  it("warning when raw text only", () => {
    const o = describeWorkspacePdfParseOutcome(emptyExtracted(), "hello pdf", []);
    expect(o.tone).toBe("warning");
    expect(o.headline.toLowerCase()).toContain("no fields");
  });

  it("warning when nothing extracted", () => {
    const o = describeWorkspacePdfParseOutcome(emptyExtracted(), "   ", []);
    expect(o.tone).toBe("warning");
    expect(o.headline.toLowerCase()).toContain("no usable text");
  });
});
