/**
 * Task 12 — Create load must navigate to /loads/:id after promote.
 */
import { describe, expect, it } from "vitest";

const pageSource = await import("./LoadWorkspacePage.tsx?raw").then((m) => m.default as string);
const appSource = await import("../App.tsx?raw").then((m) => m.default as string);

describe("load workspace promote navigation (Task 12)", () => {
  it("promote uses ensureServerDraft without syncing to draft URL mid-flight", () => {
    expect(pageSource).toContain("ensureServerDraft({ syncRoute: false })");
  });

  it("navigates to load detail after promote with validated load id", () => {
    expect(pageSource).toContain("navigate(OPS.LOAD_DETAIL(loadId), { replace: true })");
  });

  it("remounts workspace for load detail but not new→draft (parse timer)", () => {
    expect(pageSource).toContain("loadWorkspaceRemountKey(location.pathname)");
    expect(pageSource).not.toMatch(/key=\{location\.pathname\}/);
  });

  it("routes use LoadWorkspacePageRoute wrapper", () => {
    expect(appSource).toContain("LoadWorkspacePageRoute");
  });
});
