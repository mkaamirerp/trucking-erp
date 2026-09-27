import { describe, expect, it } from "vitest";
import { buildBvdUploadCompletedPath, readBvdUploadCompletion } from "./bvdUploadCompletion";

describe("bvdUploadCompletion", () => {
  it("builds and reads completed upload query", () => {
    const path = buildBvdUploadCompletedPath("972201");
    expect(path).toContain("bvdCompleted=1");
    expect(path).toContain("invoice=972201");
    expect(readBvdUploadCompletion(path.split("?")[1] ?? "")).toEqual({ invoiceNumber: "972201" });
  });
});
