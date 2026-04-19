import { describe, expect, it } from "vitest";
import { buildWorkspacePdfParseAppliedLabels } from "./loadParseAppliedLabels";
import type { LoadDocumentParseExtracted } from "../api";

const emptyEx = (): LoadDocumentParseExtracted => ({
  references: [],
  stops: [],
});

describe("buildWorkspacePdfParseAppliedLabels", () => {
  it("includes broker matched and stops when applicable", () => {
    const ex: LoadDocumentParseExtracted = {
      ...emptyEx(),
      broker_name_snapshot: "Acme",
      broker_mc_number_snapshot: "123456",
      stops: [{ stop_type: "pickup", sequence: 0, city: "Dallas" }],
    };
    const labels = buildWorkspacePdfParseAppliedLabels(ex, "hello", {
      mcOrDotAttempted: true,
      resolvedBrokerId: 99,
      brokerContactMatched: false,
    });
    expect(labels).toContain("Broker name");
    expect(labels).toContain("Broker matched (MC/DOT)");
    expect(labels).toContain("Stops");
    expect(labels).toContain("Notes / source text");
  });

  it("shows MC/DOT no match when lookup returns null", () => {
    const ex: LoadDocumentParseExtracted = {
      ...emptyEx(),
      broker_dot_number_snapshot: "999",
    };
    const labels = buildWorkspacePdfParseAppliedLabels(ex, "", {
      mcOrDotAttempted: true,
      resolvedBrokerId: null,
      brokerContactMatched: false,
    });
    expect(labels).toContain("MC/DOT from document (no tenant match)");
    expect(labels).not.toContain("Broker matched (MC/DOT)");
  });

  it("omits notes when final composed body is empty", () => {
    const ex: LoadDocumentParseExtracted = { ...emptyEx(), miles: 100 };
    const labels = buildWorkspacePdfParseAppliedLabels(ex, "   ", {
      mcOrDotAttempted: false,
      resolvedBrokerId: null,
      brokerContactMatched: false,
    });
    expect(labels).toContain("Miles");
    expect(labels).not.toContain("Notes / source text");
  });

  it("includes notes when customs line only populates body", () => {
    const ex: LoadDocumentParseExtracted = {
      ...emptyEx(),
      customs_broker_name: "CBP Partner",
    };
    const labels = buildWorkspacePdfParseAppliedLabels(ex, "", {
      mcOrDotAttempted: false,
      resolvedBrokerId: null,
      brokerContactMatched: false,
    });
    expect(labels).toContain("Notes / source text");
  });

  it("includes directory match line when flagged", () => {
    const ex: LoadDocumentParseExtracted = {
      ...emptyEx(),
      broker_contact_name_snapshot: "Jane",
    };
    const labels = buildWorkspacePdfParseAppliedLabels(ex, "", {
      mcOrDotAttempted: false,
      resolvedBrokerId: null,
      brokerContactMatched: true,
    });
    expect(labels).toContain("Broker contact (matched to directory)");
    expect(labels).toContain("Broker contact name");
  });

  it("ignores references array (not mapped by handler)", () => {
    const ex: LoadDocumentParseExtracted = {
      ...emptyEx(),
      references: [{ kind: "PO", value: "X1" }],
    };
    const labels = buildWorkspacePdfParseAppliedLabels(ex, "", {
      mcOrDotAttempted: false,
      resolvedBrokerId: null,
      brokerContactMatched: false,
    });
    expect(labels.length).toBe(0);
  });
});
