import { describe, expect, it } from "vitest";
import {
  buildLoadsDirectoryRows,
  draftTitleFromFields,
  missingLineForFields,
} from "./draftListPresentation";
import { initialWorkspaceFieldsManual } from "./loadWorkspaceShared";

describe("draftListPresentation", () => {
  it("prefers broker + route for title", () => {
    const fields = {
      ...initialWorkspaceFieldsManual(),
      brokerNameSnapshot: "Acme",
      draftStops: [
        { ...initialWorkspaceFieldsManual().draftStops[0], city: "Dallas", state_or_province: "TX" },
        { ...initialWorkspaceFieldsManual().draftStops[1], city: "Houston", state_or_province: "TX" },
      ],
    };
    expect(draftTitleFromFields(fields, null)).toMatch(/Acme/);
    expect(draftTitleFromFields(fields, null)).toMatch(/Dallas/);
  });

  it("falls back to Untitled draft", () => {
    expect(draftTitleFromFields(initialWorkspaceFieldsManual(), null)).toBe("Untitled draft");
  });

  it("formats missing line for incomplete fields", () => {
    const line = missingLineForFields(initialWorkspaceFieldsManual(), []);
    expect(line).toMatch(/^Not provided:/);
    expect(line).toMatch(/Broker load # \/ PO #/);
  });

  it("includes workspace drafts in directory with draft status", () => {
    const fields = {
      ...initialWorkspaceFieldsManual(),
      brokerNameSnapshot: "Acme",
      rate: "1200",
      draftStops: [
        { ...initialWorkspaceFieldsManual().draftStops[0], city: "Dallas", state_or_province: "TX" },
        { ...initialWorkspaceFieldsManual().draftStops[1], city: "Houston", state_or_province: "TX" },
      ],
    };
    const rows = buildLoadsDirectoryRows(
      [],
      [],
      [
        {
          id: "draft-uuid-1",
          status: "draft",
          draft_json: fields as unknown as Record<string, unknown>,
          concurrency_version: 1,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-02T00:00:00Z",
          pdf_filename: "rc.pdf",
          tenant_id: 1,
          source_channel: "manual",
          promoted_load_id: null,
          email_thread_id: null,
        },
      ],
      "",
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].status).toBe("draft");
    expect(rows[0].kind).toBe("workspace_draft");
    expect(rows[0].route).toMatch(/Dallas/);
  });
});
