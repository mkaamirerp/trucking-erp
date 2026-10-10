/**
 * Issue 0C Slice 1 — primary Dispatch + workspace Dispatch nav → Trip Container.
 */
import { describe, expect, it } from "vitest";
import { OPS } from "../routes";
import { dispatchLinks } from "./TopNav";

const SOURCES = import.meta.glob<string>(
  ["../pages/LoadWorkspacePage.tsx", "../pages/TripWorkspacePage.tsx"],
  { query: "?raw", import: "default", eager: true },
);

function source(path: string): string {
  const text = SOURCES[path];
  expect(text, path).toBeTypeOf("string");
  return text as string;
}

describe("Issue 0C Slice 1 — Dispatch nav → Trip Container", () => {
  it("F1: primary Dispatch TopNav link targets Trip Container, not legacy /dispatch", () => {
    expect(OPS.TRIP_CONTAINER).toBe("/trips/container");
    expect(OPS.DISPATCH).toBe("/dispatch");
    expect(dispatchLinks[0]).toEqual({ label: "Dispatch", to: OPS.TRIP_CONTAINER });
    expect(dispatchLinks[0].to).not.toBe(OPS.DISPATCH);
    const dispatchTos = dispatchLinks.filter((l) => l.label === "Dispatch").map((l) => l.to);
    expect(dispatchTos).toEqual([OPS.TRIP_CONTAINER]);
  });

  it("F2: Load Workspace operational Dispatch button navigates to Trip Container", () => {
    const page = source("../pages/LoadWorkspacePage.tsx");
    expect(page).toMatch(/data-testid="load-workspace-dispatch-nav"/);
    expect(page).toMatch(
      /data-testid="load-workspace-dispatch-nav"[\s\S]*?navigate\(OPS\.TRIP_CONTAINER\)/,
    );
    expect(page).not.toMatch(
      /data-testid="load-workspace-dispatch-nav"[\s\S]*?navigate\(OPS\.DISPATCH\)/,
    );
  });

  it("F2: Trip Workspace operational Dispatch button navigates to Trip Container", () => {
    const page = source("../pages/TripWorkspacePage.tsx");
    expect(page).toMatch(/data-testid="trip-workspace-dispatch-nav"/);
    expect(page).toMatch(
      /data-testid="trip-workspace-dispatch-nav"[\s\S]*?navigate\(OPS\.TRIP_CONTAINER\)/,
    );
    expect(page).not.toMatch(
      /data-testid="trip-workspace-dispatch-nav"[\s\S]*?navigate\(OPS\.DISPATCH\)/,
    );
  });

  it("changed operational Dispatch nav targets do not point at legacy /dispatch", () => {
    expect(dispatchLinks.find((l) => l.label === "Dispatch")?.to).not.toBe("/dispatch");
    const load = source("../pages/LoadWorkspacePage.tsx");
    const trip = source("../pages/TripWorkspacePage.tsx");
    const loadBtn = load.match(
      /data-testid="load-workspace-dispatch-nav"[\s\S]{0,200}?navigate\((OPS\.[A-Z_]+)\)/,
    );
    const tripBtn = trip.match(
      /data-testid="trip-workspace-dispatch-nav"[\s\S]{0,200}?navigate\((OPS\.[A-Z_]+)\)/,
    );
    expect(loadBtn?.[1]).toBe("OPS.TRIP_CONTAINER");
    expect(tripBtn?.[1]).toBe("OPS.TRIP_CONTAINER");
  });
});
