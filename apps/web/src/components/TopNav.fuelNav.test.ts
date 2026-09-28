import { describe, expect, it } from "vitest";
import { OPS, ADMIN } from "../routes";
import { financeLinks, settingsGroups } from "./TopNav";

describe("TopNav fuel navigation consolidation", () => {
  it("exposes exactly one Fuel link in Finance top nav", () => {
    const fuelLinks = financeLinks.filter((l) => l.to === OPS.FUEL || l.label === "Fuel");
    expect(fuelLinks).toEqual([{ label: "Fuel", to: OPS.FUEL }]);
    expect(financeLinks[0]).toEqual({ label: "Fuel", to: OPS.FUEL });
  });

  it("does not expose Fuel workflow entries in Settings > Integrations", () => {
    const integrations = settingsGroups.find((g) => g.label === "Integrations");
    expect(integrations).toBeDefined();
    const labels = integrations!.items.map((i) => i.label);
    const tos = integrations!.items.map((i) => i.to);
    expect(labels).not.toContain("Fuel");
    expect(labels).not.toContain("Fuel Providers");
    expect(labels).not.toContain("Fuel Review");
    expect(labels).not.toContain("BVD Extract");
    expect(labels).not.toContain("Fuel home");
    expect(tos).not.toContain(OPS.FUEL_PROVIDERS);
    expect(tos).not.toContain(OPS.FUEL_REVIEW);
    expect(tos).not.toContain(OPS.FUEL_BVD_UPLOAD);
    expect(tos).not.toContain(ADMIN.INTEGRATIONS_FUEL);
  });
});
