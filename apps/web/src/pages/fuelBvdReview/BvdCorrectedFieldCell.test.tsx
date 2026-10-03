import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdRow } from "../../api";
import BvdCorrectedFieldCell from "./BvdCorrectedFieldCell";

function row(partial: Partial<FuelBvdRow> & Pick<FuelBvdRow, "id" | "row_type">): FuelBvdRow {
  return { import_id: "imp", ...partial } as FuelBvdRow;
}

describe("BvdCorrectedFieldCell", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("shows effective value with mark in processing review", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    const r = row({
      id: 2,
      row_type: "TRANSACTION",
      final_amt: "1,610.96",
      field_corrections: {
        final_amt: { extracted_value: "1,610.96", reviewed_value: "1,610.86" },
      },
    });
    act(() => {
      root.render(
        <BvdCorrectedFieldCell row={r} field="final_amt" presentation="processing-review" />,
      );
    });
    expect(container.textContent).toContain("1,610.86");
    expect(container.textContent).toContain("*");
  });

  it("draft mode exposes edit trigger when onFieldDraft is set", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    const r = row({
      id: 2,
      row_type: "TRANSACTION",
      final_amt: "272.00",
    });
    act(() => {
      root.render(
        <BvdCorrectedFieldCell
          row={r}
          field="final_amt"
          presentation="processing-review"
          onFieldDraft={vi.fn()}
        />,
      );
    });
    expect(container.querySelector("button.bvd-inline-edit-trigger")).toBeTruthy();
  });

  it("shows extracted line on processed detail", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    const r = row({
      id: 2,
      row_type: "TRANSACTION",
      final_amt: "1,610.96",
      field_corrections: {
        final_amt: { extracted_value: "1,610.96", reviewed_value: "1,610.86" },
      },
    });
    act(() => {
      root.render(
        <BvdCorrectedFieldCell row={r} field="final_amt" presentation="full-stored-detail" />,
      );
    });
    expect(container.textContent).toContain("1,610.86");
    expect(container.textContent).toContain("Extracted: 1,610.96");
    expect(container.textContent).toContain("Corrected during review");
  });
});
