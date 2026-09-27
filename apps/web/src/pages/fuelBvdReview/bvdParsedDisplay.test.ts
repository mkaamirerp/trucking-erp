import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { displayCell, sortBvdRows } from "./bvdParsedDisplay";

describe("bvdParsedDisplay", () => {
  it("sorts transactions after header", () => {
    const rows: FuelBvdRow[] = [
      { id: 2, import_id: "x", row_type: "TRANSACTION", source_row_number: 1 } as FuelBvdRow,
      { id: 1, import_id: "x", row_type: "HEADER", source_page: 1 } as FuelBvdRow,
    ];
    const sorted = sortBvdRows(rows);
    expect(sorted[0].row_type).toBe("HEADER");
  });

  it("displayCell returns empty for blank", () => {
    const row = { id: 1, import_id: "x", row_type: "HEADER", client_email: "" } as FuelBvdRow;
    expect(displayCell(row, "client_email")).toBe("");
  });
});
