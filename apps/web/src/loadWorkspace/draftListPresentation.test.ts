import { describe, expect, it } from "vitest";
import {
  associatedTripDriverLabel,
  associatedTripNumber,
  buildLoadsDirectoryRows,
  draftTitleFromFields,
  loadToDirectoryRow,
  missingLineForFields,
} from "./draftListPresentation";
import { initialWorkspaceFieldsManual } from "./loadWorkspaceShared";

function loadRow(partial: Record<string, unknown>) {
  return {
    id: 1,
    load_number: "Oct-26-0332",
    status: "ready",
    ...partial,
  } as never;
}

describe("associated trip display", () => {
  it("shows the planned trip number and that trip's driver", () => {
    const load = loadRow({
      trip_number: null,
      active_trip_id: null,
      driver: null,
      open_planned_trip_id: 919,
      open_planned_trip_number: "T1E2173910001",
      open_planned_trip_driver_name: "Pat Driver",
    });
    expect(associatedTripNumber(load)).toBe("T1E2173910001");
    expect(associatedTripDriverLabel(load)).toBe("Pat Driver");
    expect(loadToDirectoryRow(load).tripNumber).toBe("T1E2173910001");
    expect(loadToDirectoryRow(load).driver).toBe("Pat Driver");
  });

  it("shows the assigned trip number and that trip's driver", () => {
    const load = loadRow({
      trip_number: "T-ACTIVE-1",
      active_trip_id: 40,
      active_membership_trip_number: "T-ACTIVE-1",
      active_membership_driver_name: "Sam Driver",
      driver: null,
      open_planned_trip_number: null,
    });
    expect(associatedTripNumber(load)).toBe("T-ACTIVE-1");
    expect(associatedTripDriverLabel(load)).toBe("Sam Driver");
  });

  it("leaves trip number and driver blank when the load has no trip", () => {
    const load = loadRow({
      trip_number: null,
      active_trip_id: null,
      driver: { first_name: "Unused", last_name: "Driver" },
      open_planned_trip_number: null,
    });
    expect(associatedTripNumber(load)).toBe("");
    expect(associatedTripDriverLabel(load)).toBe("");
    expect(loadToDirectoryRow(load).tripNumber).toBe("—");
    expect(loadToDirectoryRow(load).driver).toBe("—");
  });
});

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
