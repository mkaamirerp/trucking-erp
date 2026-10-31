import { describe, expect, it } from "vitest";
import { loadAuditActionLabel } from "./loadAuditLabels";

describe("loadAuditActionLabel", () => {
  it("maps load history actions to friendly labels", () => {
    expect(loadAuditActionLabel("load_created")).toBe("Load created");
    expect(loadAuditActionLabel("load_updated")).toBe("Load updated");
    expect(loadAuditActionLabel("load_marked_ready")).toBe("Marked ready");
    expect(loadAuditActionLabel("load_cancelled")).toBe("Load cancelled");
    expect(loadAuditActionLabel("load_stops_changed")).toBe("Pickup / delivery changed");
    expect(loadAuditActionLabel("load_revised_rc_attached")).toBe("Revised RC uploaded");
    expect(loadAuditActionLabel("load_reparse_pdf_accepted")).toBe("Revised RC saved");
    expect(loadAuditActionLabel("pod_evidence_uploaded")).toBe("POD uploaded");
  });

  it("falls back to the raw action", () => {
    expect(loadAuditActionLabel("custom_action")).toBe("custom_action");
  });
});
