import { describe, expect, it } from "vitest";
import { buildParseEngineAttribution } from "./loadParseEngineAttribution";

describe("buildParseEngineAttribution", () => {
  it("formats Claude Haiku with timings", () => {
    const line = buildParseEngineAttribution(
      {
        llm_provider: "anthropic",
        llm_model: "claude-haiku-4-5-20251001",
        semantic_ms: 12000,
        server_parse_ms: 12500,
      },
      { parseRequestMs: 47000, totalMs: 47200 },
    );
    expect(line).toContain("Claude");
    expect(line).toContain("claude-haiku-4-5-20251001");
    expect(line).toContain("model 12.0s");
    expect(line).toContain("request 47.0s");
  });
});
