import { describe, expect, it } from "vitest";
import {
  friendlyMergeErrorMessage,
  mergeExecuteStatusLabel,
  mergeResolutionFieldLabel,
} from "./globalBookingBrokerMergeErrors";

describe("friendlyMergeErrorMessage", () => {
  it("maps known merge codes", () => {
    expect(friendlyMergeErrorMessage("merge_preview_stale")).toContain("changed");
    expect(friendlyMergeErrorMessage("merge_regulatory_blocking_conflict")).toContain("CVOR");
  });

  it("maps merge_resolution_required with field label", () => {
    const msg = friendlyMergeErrorMessage("merge_resolution_required:legal_name");
    expect(msg).toContain("legal name");
    expect(msg.toLowerCase()).toContain("choose");
  });

  it("passes through unknown codes", () => {
    expect(friendlyMergeErrorMessage("some_new_code")).toBe("some_new_code");
  });
});

describe("mergeResolutionFieldLabel", () => {
  it("labels known fields", () => {
    expect(mergeResolutionFieldLabel("display_name")).toBe("display name");
  });
});

describe("mergeExecuteStatusLabel", () => {
  it("describes already completed", () => {
    expect(mergeExecuteStatusLabel("already_completed")).toContain("already");
  });
});
