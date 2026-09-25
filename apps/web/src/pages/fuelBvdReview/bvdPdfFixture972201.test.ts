/**
 * Semantic match checks against the real BVD 972201 PDF (page 2 Grand Total row).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { mapPdfJsTextItems, resolveSemanticTextMatch } from "./bvdPdfHighlight";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../../..");
const pdfPath = join(repoRoot, "docs/fixtures/fuel/BVD_invoice_972201.pdf");

function ensurePromiseWithResolvers() {
  if (!Promise.withResolvers) {
    Promise.withResolvers = function <T>() {
      let resolve!: (value: T | PromiseLike<T>) => void;
      let reject!: (reason?: unknown) => void;
      const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      return { promise, resolve, reject };
    };
  }
}

describe("BVD_invoice_972201 PDF semantic highlights", () => {
  let page2Items: ReturnType<typeof mapPdfJsTextItems>;

  beforeAll(async () => {
    ensurePromiseWithResolvers();
    const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
    const data = new Uint8Array(readFileSync(pdfPath));
    const doc = await pdfjs.getDocument({ data, useWorkerFetch: false, isEvalSupported: false }).promise;
    const page = await doc.getPage(2);
    const text = await page.getTextContent();
    page2Items = mapPdfJsTextItems(
      text.items.filter((i): i is { str: string; transform: number[]; width: number; height: number } => "str" in i),
    );
    await doc.destroy();
  }, 60_000);

  const grandTotalCases = [
    { field: "qty", value: "1,474.00", product: "TA" },
    { field: "pre_tax_amt", value: "3,027.44", product: "TA" },
    { field: "hst", value: "393.57", product: "TA" },
    { field: "final_amount", value: "3,421.01", product: "TA" },
    { field: "currency", value: "CN", product: "TA" },
  ];

  for (const { field, value, product } of grandTotalCases) {
    it(`page 2 Grand Total ${field}=${value} has unique semantic match`, () => {
      const match = resolveSemanticTextMatch(page2Items, {
        page: 2,
        field,
        label: field,
        value,
        rowType: "GRAND_TOTAL",
        sourceRowNumber: 1,
        selectionKey: `gt:${field}`,
        anchorField: "product",
        anchorValue: product,
        rowQtyHint: "1,474.00",
      });
      expect(match).not.toBeNull();
      expect(match!.ambiguous).toBe(false);
      expect(match!.itemIndices.length).toBeGreaterThan(0);
    });
  }

  it("page 2 has multiple exact TA tokens (table + legend)", () => {
    const taCount = page2Items.filter((it) => it.str.trim() === "TA").length;
    expect(taCount).toBeGreaterThan(1);
  });

  it("disambiguates Grand Total GST 0.00 on TA row using product anchor", () => {
    const match = resolveSemanticTextMatch(page2Items, {
      page: 2,
      field: "gst",
      label: "GST",
      value: "0.00",
      rowType: "GRAND_TOTAL",
      sourceRowNumber: 1,
      selectionKey: "gt:gst",
      anchorField: "product",
      anchorValue: "TA",
      rowQtyHint: "1,474.00",
    });
    expect(match).not.toBeNull();
    expect(match!.ambiguous).toBe(false);
  });
});
