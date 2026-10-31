import { describe, expect, it } from "vitest";
import { parseReparseOtherLoadMatch, REPARSE_MATCHES_OTHER_LOAD } from "./api";

describe("parseReparseOtherLoadMatch", () => {
  it("returns candidates when FastAPI detail uses REPARSE_MATCHES_OTHER_LOAD", () => {
    const err = new Error(
      JSON.stringify({
        detail: {
          code: REPARSE_MATCHES_OTHER_LOAD,
          message: "This PDF matches a different load. Nothing was changed.",
          candidates: [
            {
              match_type: "exact_pdf_sha256",
              load_id: 42,
              load_number: "90042",
              broker_name: null,
              broker_load_reference: null,
              load_status: "ready",
              pickup: "Toronto, ON",
              delivery: "Montreal, QC",
              trip_id: null,
              trip_status: null,
              driver_id: 5,
              truck_id: null,
              trailer_id: null,
            },
          ],
        },
      }),
    );
    const parsed = parseReparseOtherLoadMatch(err);
    expect(parsed?.candidates[0]?.pickup).toBe("Toronto, ON");
    expect(parsed?.candidates[0]?.driver_id).toBe(5);
  });

  it("returns null for plain string detail", () => {
    const err = new Error(JSON.stringify({ detail: "This PDF matches a different load." }));
    expect(parseReparseOtherLoadMatch(err)).toBeNull();
  });
});
