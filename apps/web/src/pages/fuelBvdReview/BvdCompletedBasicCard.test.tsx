import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import BvdCompletedBasicCard from "./BvdCompletedBasicCard";
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

describe("BvdCompletedBasicCard", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("F: invoice number links to full stored detail", () => {
    const view = buildBvdCompletedBasicView(goldenRows(), "import-972201");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <MemoryRouter>
          <BvdCompletedBasicCard view={view} />
        </MemoryRouter>,
      );
    });
    const link = container.querySelector('[data-testid="bvd-invoice-detail-link"]') as HTMLAnchorElement;
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toBe("/fuel/bvd/import-972201/detail");
  });

  it("I: history card is read-only", () => {
    const view = buildBvdCompletedBasicView(goldenRows(), "import-972201");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <MemoryRouter>
          <BvdCompletedBasicCard view={view} />
        </MemoryRouter>,
      );
    });
    const article = container.querySelector("article");
    expect(article?.getAttribute("data-read-only")).toBe("true");
  });
});
