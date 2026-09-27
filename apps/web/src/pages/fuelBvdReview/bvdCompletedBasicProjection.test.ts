import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { buildBvdCompletedBasicView } from "./bvdCompletedBasicProjection";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../../..");
const golden = JSON.parse(
  readFileSync(join(repoRoot, "tests/fixtures/fuel_bvd_972201_expected.json"), "utf-8"),
) as { rows: Record<string, unknown>[] };

function goldenRows(): FuelBvdRow[] {
  return golden.rows.map((r, i) => ({
    id: i + 1,
    import_id: "import-972201",
    review_status: "SOURCE_REVIEWED",
    ...r,
  })) as FuelBvdRow[];
}

describe("buildBvdCompletedBasicView", () => {
  it("A: shows only HST when GST/PST/QST are zero", () => {
    const view = buildBvdCompletedBasicView(goldenRows(), "import-972201");
    expect(view.taxes.map((t) => t.key)).toEqual(["hst"]);
    expect(view.taxes[0]?.amount).toBe("393.57");
  });

  it("B: shows GST + PST when HST is zero", () => {
    const rows = goldenRows();
    const grand = rows.find((r) => r.row_type === "GRAND_TOTAL" && r.row_label === "Grand Total");
    if (grand) {
      grand.hst = "0.00";
      grand.gst = "72.14";
      grand.pst = "31.00";
    }
    const view = buildBvdCompletedBasicView(rows, "import-972201");
    expect(view.taxes.map((t) => t.key).sort()).toEqual(["gst", "pst"]);
  });

  it("C: omits taxes when all are zero", () => {
    const rows = goldenRows();
    const grand = rows.find((r) => r.row_type === "GRAND_TOTAL" && r.row_label === "Grand Total");
    if (grand) {
      grand.hst = "0.00";
      grand.gst = "0.00";
      grand.pst = "0.00";
      grand.qst = "0.00";
    }
    const view = buildBvdCompletedBasicView(rows, "import-972201");
    expect(view.taxes).toEqual([]);
  });

  it("D: shows only Fuel/TA when DEF/Scale/Cash are zero", () => {
    const view = buildBvdCompletedBasicView(goldenRows(), "import-972201");
    expect(view.categories.map((c) => c.key)).toEqual(["TA"]);
    expect(view.categories[0]?.label).toBe("Fuel / TA");
  });

  it("E: includes DEF when non-zero", () => {
    const rows = goldenRows();
    const def = rows.find((r) => r.row_type === "GRAND_TOTAL" && r.product === "DF");
    if (def) def.final_amount = "125.50";
    const view = buildBvdCompletedBasicView(rows, "import-972201");
    expect(view.categories.some((c) => c.key === "DF")).toBe(true);
  });

  it("I: completed basic view is read-only when SOURCE_REVIEWED", () => {
    const view = buildBvdCompletedBasicView(goldenRows(), "import-972201");
    expect(view.readOnly).toBe(true);
  });
});
