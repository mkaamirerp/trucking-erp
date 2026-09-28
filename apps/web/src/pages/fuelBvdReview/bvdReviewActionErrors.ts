/** Parse FastAPI errors for BVD save/process actions (visible operator feedback). */

type ReconciliationCheck = {
  code?: string;
  status?: string;
  difference?: string;
  detail?: string;
  expected?: string;
  actual?: string;
};

export function formatFuelBvdReviewActionError(err: unknown): string {
  if (!(err instanceof Error)) {
    return "Request failed";
  }
  const raw = err.message.trim();
  if (!raw.startsWith("{")) {
    return raw.length > 0 && raw.length < 600 ? raw : "Request failed";
  }
  try {
    const body = JSON.parse(raw) as { detail?: unknown };
    const detail = body.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (detail && typeof detail === "object") {
      const d = detail as Record<string, unknown>;
      if (d.code === "BVD_REVIEW_LOCKED") {
        return typeof d.message === "string"
          ? d.message
          : "BVD source review is complete; corrections are locked.";
      }
      if (d.code === "BVD_SOURCE_RECONCILIATION_FAILED") {
        const parts: string[] = ["Source reconciliation failed"];
        if (typeof d.message === "string") {
          parts.push(d.message);
        }
        const reconciliation = d.reconciliation as { checks?: ReconciliationCheck[] } | undefined;
        const fails = (reconciliation?.checks ?? []).filter((c) => c.status === "FAIL");
        for (const check of fails.slice(0, 8)) {
          const bit = check.code ?? "CHECK";
          const delta = check.difference && check.difference !== "0.00" ? ` Δ ${check.difference}` : "";
          parts.push(`${bit}${delta}`);
        }
        return parts.join(" · ");
      }
      if (typeof d.message === "string") {
        return d.message;
      }
    }
  } catch {
    /* fall through */
  }
  return raw.length < 600 ? raw : "Request failed";
}
