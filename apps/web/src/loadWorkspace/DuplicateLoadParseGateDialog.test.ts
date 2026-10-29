import { describe, expect, it } from "vitest";
import { formatDuplicateLoadRoute } from "./DuplicateLoadParseGateDialog";

describe("formatDuplicateLoadRoute", () => {
  it("formats city state arrow line", () => {
    expect(
      formatDuplicateLoadRoute({
        match_type: "exact_pdf_sha256",
        load_id: 1,
        load_number: "1001",
        broker_name: "Armstrong",
        broker_load_reference: "PO-1",
        load_status: "ready",
        pickup: "Brantford, ON",
        delivery: "Romeoville, IL",
        trip_id: null,
        trip_status: null,
        driver_id: null,
        truck_id: null,
        trailer_id: null,
      }),
    ).toBe("Brantford, ON → Romeoville, IL");
  });
});
