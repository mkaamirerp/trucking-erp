import { describe, expect, it } from "vitest";
import { draftTitleFromFields, missingLineForFields } from "./draftListPresentation";
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
});
