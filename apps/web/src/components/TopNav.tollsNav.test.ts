import { describe, expect, it } from "vitest";
import { OPS } from "../routes";
import { financeLinks } from "./TopNav";

describe("TopNav Tolls history link", () => {
    it("exposes exactly one Tolls link in Finance next to Fuel at /tolls", () => {
    const tollsLinks = financeLinks.filter((l) => l.to === OPS.TOLLS || l.label === "Tolls");
    expect(tollsLinks).toEqual([{ label: "Tolls", to: OPS.TOLLS }]);
    expect(financeLinks[1]).toEqual({ label: "Tolls", to: OPS.TOLLS });
    expect(OPS.TOLLS).toBe("/tolls");
  });
});
