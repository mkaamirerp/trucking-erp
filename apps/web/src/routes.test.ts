import { describe, expect, it } from "vitest";
import { OPS } from "./routes";

describe("Load workspace routes", () => {
  it("opens a Load without the removed dispatch-assignment query mode", () => {
    expect(OPS.LOAD_DETAIL(42)).toBe("/loads/42");
    expect(OPS).not.toHaveProperty("LOAD_DISPATCH_ASSIGN_QUERY");
  });
});
