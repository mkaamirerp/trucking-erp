import type { DraftStop } from "./loadWorkspaceShared";

const WRITABLE = new Set(["PICKUP", "DROP", "DELIVERY"]);

/** Issue I19 — block save until operator classifies parsed/unknown stop types. */
export function validateDraftStopsClassifiedForSave(draftStops: DraftStop[]): string | null {
  for (const s of draftStops) {
    const t = (s.stop_type || "").trim().toUpperCase();
    if (!WRITABLE.has(t)) {
      const hint = s.parseStopTypeEvidence?.trim();
      const suffix = hint ? ` (parser value: ${hint})` : "";
      return `Stop #${(s.sequence ?? 0) + 1} needs an explicit type (Pickup, Delivery, or Drop) before save.${suffix}`;
    }
  }
  return null;
}

export function isWritableStopType(stopType: string | null | undefined): boolean {
  return WRITABLE.has((stopType || "").trim().toUpperCase());
}
