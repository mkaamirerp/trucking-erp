import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/** Task 17 — condensed form must expose every classic field (visible or under More). */
const REQUIRED_KEYS = [
  "brokerId",
  "brokerContactId",
  "brokerNameSnapshot",
  "brokerContactNameSnapshot",
  "brokerContactPhoneSnapshot",
  "brokerContactExtensionSnapshot",
  "brokerContactEmailSnapshot",
  "brokerLoadReference",
  "rate",
  "customerRate",
  "miles",
  "freightMode",
  "equipmentType",
  "trailerType",
  "trailerSize",
  "commodity",
  "estimatedWeight",
  "palletCaseCount",
  "temperatureRequirement",
  "hazmat",
  "customsBrokerId",
  "internalNotes",
  "notes",
  "commodity_notes",
  "stop_type",
  "sequence",
  "country",
] as const;

describe("load workspace field parity", () => {
  it("condensed form source references all required data keys", () => {
    const src = readFileSync(
      resolve(import.meta.dirname, "LoadWorkspaceCondensedForm.tsx"),
      "utf8",
    );
    for (const key of REQUIRED_KEYS) {
      expect(src, `missing ${key}`).toMatch(new RegExp(key.replace(/_/g, "_")));
    }
    expect(src).toContain("data-testid=\"load-workspace-condensed\"");
  });

  it("classic layout is not rendered from LoadWorkspaceForm", () => {
    const form = readFileSync(resolve(import.meta.dirname, "LoadWorkspaceForm.tsx"), "utf8");
    expect(form).not.toContain("lg:grid-cols-2");
    expect(form).toContain("LoadWorkspaceCondensedForm");
  });
});
