/**
 * Create load must navigate to dispatch home after promote so the load appears in Loads to assign.
 */
import { describe, expect, it } from "vitest";

const pageSource = await import("./LoadWorkspacePage.tsx?raw").then((m) => m.default as string);
const appSource = await import("../App.tsx?raw").then((m) => m.default as string);

describe("load workspace promote navigation (Task 12)", () => {
  it("promote uses ensureServerDraft without syncing to draft URL mid-flight", () => {
    expect(pageSource).toContain("ensureServerDraft({ syncRoute: false })");
  });

  it("manual parse persists PDF on draft at upload (single AI parse before create load)", () => {
    expect(pageSource).toContain("parseLoadWorkspaceDraftDocument(manualDraftId, file");
    expect(pageSource).not.toContain("flushPendingWorkspaceParseToDraft");
    expect(pageSource).not.toContain("pendingWorkspaceParseRef");
  });

  it("ensureServerDraft reuses in-memory workspace draft id (save after parse on /loads/new)", () => {
    expect(pageSource).toContain('workspaceDraft?.status === "draft" && workspaceDraft.id');
  });

  it("navigates to dispatch home after promote with validated load id", () => {
    expect(pageSource).toContain("navigate(OPS.DASHBOARD, { replace: true })");
    expect(pageSource).toMatch(
      /const loadId = Number\(result\.load_id\)[\s\S]*navigate\(OPS\.DASHBOARD/,
    );
  });

  it("remounts workspace for load detail but not new→draft (parse timer)", () => {
    expect(pageSource).toContain("loadWorkspaceRemountKey(location.pathname)");
    expect(pageSource).not.toMatch(/key=\{location\.pathname\}/);
  });

  it("routes use LoadWorkspacePageRoute wrapper", () => {
    expect(appSource).toContain("LoadWorkspacePageRoute");
  });
});
