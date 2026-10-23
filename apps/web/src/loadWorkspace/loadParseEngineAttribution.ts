/** Human-readable parse LLM attribution from API `context` (provider, model, timings). */

export type ParseWallClockTiming = {
  /** Time until parse HTTP response (upload + server semantic call). */
  parseRequestMs?: number;
  /** Full client wait including hydration after response. */
  totalMs?: number;
};

function formatSeconds(ms: number | undefined): string | null {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function providerLabel(raw: string): string {
  const p = raw.trim().toLowerCase();
  if (p === "anthropic" || p === "claude") return "Claude";
  if (p === "openai") return "OpenAI";
  return raw.trim() || "unknown";
}

export function buildParseEngineAttribution(
  context: Record<string, unknown> | null | undefined,
  wall?: ParseWallClockTiming,
): string | null {
  const ctx = context ?? {};
  const provider = providerLabel(String(ctx.llm_provider ?? ""));
  const model = String(ctx.llm_model ?? "").trim();
  const semanticMs =
    typeof ctx.openai_ms === "number"
      ? ctx.openai_ms
      : typeof ctx.semantic_ms === "number"
        ? ctx.semantic_ms
        : undefined;
  const serverMs = typeof ctx.server_parse_ms === "number" ? ctx.server_parse_ms : undefined;

  const parts: string[] = [];
  if (provider !== "unknown" || model) {
    parts.push(model ? `${provider} (${model})` : provider);
  }
  const semanticSec = formatSeconds(semanticMs);
  const serverSec = formatSeconds(serverMs);
  if (semanticSec) parts.push(`model ${semanticSec}`);
  if (serverSec && serverSec !== semanticSec) parts.push(`server ${serverSec}`);
  const requestSec = formatSeconds(wall?.parseRequestMs);
  const totalSec = formatSeconds(wall?.totalMs);
  if (requestSec) parts.push(`request ${requestSec}`);
  if (totalSec && totalSec !== requestSec) parts.push(`total ${totalSec}`);

  if (parts.length === 0) return null;
  return `Semantic engine: ${parts.join(" · ")}`;
}
