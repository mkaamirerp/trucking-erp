import { describe, expect, it } from "vitest";
import { loadWorkspaceRemountKey, OPS } from "./routes";

describe("loadWorkspaceRemountKey", () => {
  it("keeps same key for new and draft (parseBusy must survive draft navigation during upload)", () => {
    const newKey = loadWorkspaceRemountKey(OPS.LOAD_NEW);
    const draftKey = loadWorkspaceRemountKey(OPS.LOAD_DRAFT("ab85a87a-4a85-4f30-bf5b-aa6f32c01a46"));
    expect(newKey).toBe("load-workspace-pre-promote");
    expect(draftKey).toBe(newKey);
  });

  it("would remount if pathname were used as key (regression guard)", () => {
    expect(loadWorkspaceRemountKey(OPS.LOAD_NEW)).not.toBe(OPS.LOAD_NEW);
    expect(loadWorkspaceRemountKey(OPS.LOAD_DRAFT("x"))).not.toBe(OPS.LOAD_DRAFT("x"));
  });

  it("remounts per load detail id", () => {
    expect(loadWorkspaceRemountKey("/loads/42")).toBe("load-workspace-detail-42");
    expect(loadWorkspaceRemountKey("/loads/42?mode=payroll")).toBe("load-workspace-detail-42");
  });
});
