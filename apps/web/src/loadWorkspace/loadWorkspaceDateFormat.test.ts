import { describe, expect, it } from "vitest";
import { formatDateMonthFirst, parseDateMonthFirst } from "./loadWorkspaceDateFormat";

describe("loadWorkspaceDateFormat", () => {
  it("formats ISO dates month-first", () => {
    expect(formatDateMonthFirst("2026-10-28")).toBe("10/28/2026");
  });

  it("parses month-first to ISO", () => {
    expect(parseDateMonthFirst("10/28/2026")).toBe("2026-10-28");
  });
});
