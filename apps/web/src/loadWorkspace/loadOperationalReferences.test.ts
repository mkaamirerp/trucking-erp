import { describe, expect, it } from "vitest";
import { extractedStopsToDraft } from "./applyLoadDocumentParseResponse";
import {
  compactLoadReferencesForDisplay,
  displayOperationalReferenceLabel,
  loadReferencesFromLoad,
  VISIBLE_BROKER_LOAD_REFERENCE_LABEL,
  VISIBLE_INTERNAL_LOAD_NUMBER_LABEL,
  workspaceReferencesFromParse,
} from "./loadOperationalReferences";
import { workspaceFieldsFromLoad } from "./loadWorkspaceShared";
import type { Load } from "@/api";

describe("workspace reference hydration", () => {
  it("copies extracted.references into workspace state", () => {
    const copied = workspaceReferencesFromParse([
      { kind: "po_number", value: "4500123", label: "PO #", confidence: "high" },
      { kind: "", value: "drop-me" },
      { kind: "bol_number", value: "  " },
    ]);
    expect(copied).toEqual([
      { kind: "po_number", value: "4500123", label: "PO #", confidence: "high" },
    ]);
  });

  it("does not auto-attach a generic load-level reference onto a stop", () => {
    const stops = extractedStopsToDraft([
      { stop_type: "pickup", sequence: 0, city: "Dallas", reference_number: null },
      { stop_type: "delivery", sequence: 1, city: "Houston", reference_number: "STOP-OWNED" },
    ]);
    expect(stops[0].reference_number).toBeNull();
    expect(stops[1].reference_number).toBe("STOP-OWNED");
    expect(stops.every((s) => s.reference_number !== "PU-GENERIC")).toBe(true);
  });

  it("reopen restores references from GET load payload", () => {
    const load = {
      id: 1,
      status: "draft",
      load_number: "INT-1",
      broker_load_reference: "3872125-1",
      references: [{ kind: "po_number", value: "PO-9", label: "PO #" }],
      stops: [],
    } as Load;
    const fields = workspaceFieldsFromLoad(load);
    expect(fields.loadReferences).toEqual([{ kind: "po_number", value: "PO-9", label: "PO #" }]);
    expect(loadReferencesFromLoad(load.references)).toEqual(fields.loadReferences);
  });
});

describe("visible naming", () => {
  it("uses Load Number for broker_load_reference", () => {
    expect(VISIBLE_BROKER_LOAD_REFERENCE_LABEL).toBe("Load Number");
  });

  it("uses TruckERP ID for internal load_number", () => {
    expect(VISIBLE_INTERNAL_LOAD_NUMBER_LABEL).toBe("TruckERP ID");
  });

  it("maps known kinds and useful source labels", () => {
    expect(displayOperationalReferenceLabel({ kind: "po_number", value: "1" })).toBe("PO #");
    expect(
      displayOperationalReferenceLabel({ kind: "pickup_number", value: "1", label: "Pickup Ref" }),
    ).toBe("Pickup Ref");
    expect(displayOperationalReferenceLabel({ kind: "weird_kind", value: "Z" })).toBe("Reference");
  });

  it("suppresses compact display duplicates that already appear as stop reference_number", () => {
    const refs = [
      { kind: "pickup_number", value: "PU-1" },
      { kind: "po_number", value: "PO-9" },
    ];
    const compact = compactLoadReferencesForDisplay(refs, [{ reference_number: "PU-1" }]);
    expect(compact).toEqual([{ kind: "po_number", value: "PO-9" }]);
    expect(refs).toHaveLength(2);
  });
});
