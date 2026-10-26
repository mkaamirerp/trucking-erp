import { VISIBLE_BROKER_LOAD_REFERENCE_LABEL } from "@/loadWorkspace/loadOperationalReferences";

export type ParseConfidenceTier = "high" | "medium" | "low";

const TIER_RANK: Record<ParseConfidenceTier, number> = { low: 0, medium: 1, high: 2 };

export function normalizeConfidenceValue(raw: string | null | undefined): ParseConfidenceTier | null {
  const l = (raw ?? "").trim().toLowerCase();
  if (l === "high") return "high";
  if (l === "medium" || l === "med") return "medium";
  if (l === "low") return "low";
  return null;
}

/** Worst tier across parser field_confidence; parse warnings force low (review RC). */
export function worstParseConfidenceTier(
  fieldConfidence: Record<string, string> | null | undefined,
  parseWarnings?: string[] | null,
): ParseConfidenceTier {
  if ((parseWarnings?.length ?? 0) > 0) return "low";
  const tiers = Object.values(fieldConfidence ?? {})
    .map(normalizeConfidenceValue)
    .filter((t): t is ParseConfidenceTier => t != null);
  if (tiers.length === 0) return "medium";
  return tiers.reduce(
    (worst, t) => (TIER_RANK[t] < TIER_RANK[worst] ? t : worst),
    "high" as ParseConfidenceTier,
  );
}

export function parseConfidenceTierLabel(tier: ParseConfidenceTier): string {
  switch (tier) {
    case "high":
      return "High confidence";
    case "medium":
      return "Review suggested";
    case "low":
      return "Low confidence — check PDF";
  }
}

export function parseConfidenceRcPanelClasses(tier: ParseConfidenceTier): {
  border: string;
  badge: string;
  title: string;
} {
  switch (tier) {
    case "high":
      return {
        border: "border-emerald-500/50 ring-1 ring-emerald-500/20",
        badge: "bg-emerald-600 text-white",
        title: "text-emerald-800 dark:text-emerald-200",
      };
    case "medium":
      return {
        border: "border-amber-500/50 ring-1 ring-amber-500/20",
        badge: "bg-amber-600 text-white",
        title: "text-amber-900 dark:text-amber-100",
      };
    case "low":
      return {
        border: "border-red-500/50 ring-1 ring-red-500/25",
        badge: "bg-red-600 text-white",
        title: "text-red-800 dark:text-red-100",
      };
  }
}

export function parseConfidenceAppliedChipClasses(tier: ParseConfidenceTier | null): string {
  if (tier === "high") {
    return "border-emerald-500/60 bg-emerald-500/10 text-emerald-900 dark:text-emerald-100";
  }
  if (tier === "medium") {
    return "border-amber-500/60 bg-amber-500/10 text-amber-950 dark:text-amber-100";
  }
  if (tier === "low") {
    return "border-red-500/60 bg-red-500/10 text-red-900 dark:text-red-100";
  }
  return "border-[var(--trk-border)] bg-[var(--trk-bg)] text-[var(--trk-text-muted)]";
}

/** Maps applied-field chip labels to field_confidence keys from parse responses. */
const APPLIED_LABEL_CONFIDENCE_KEYS: Record<string, string[]> = {
  "Broker name": ["broker_name_snapshot"],
  "Broker contact name": ["broker_contact_name_snapshot"],
  "Broker contact phone": ["broker_contact_phone_snapshot"],
  "Broker contact email": ["broker_contact_email_snapshot"],
  [VISIBLE_BROKER_LOAD_REFERENCE_LABEL]: ["broker_load_reference"],
  Mode: ["mode"],
  "Equipment type": ["equipment_type"],
  "Trailer type": ["trailer_type"],
  "Trailer size": ["trailer_size"],
  Commodity: ["commodity"],
  "Estimated weight": ["estimated_weight"],
  Rate: ["rate"],
  "Customer rate": ["customer_rate"],
  Miles: ["miles"],
  Stops: ["stops"],
};

export function confidenceTierForAppliedLabel(
  label: string,
  fieldConfidence: Record<string, string> | null | undefined,
): ParseConfidenceTier | null {
  const fc = fieldConfidence ?? {};
  const keys = APPLIED_LABEL_CONFIDENCE_KEYS[label];
  if (!keys?.length) return null;
  const tiers = keys
    .map((k) => normalizeConfidenceValue(fc[k]))
    .filter((t): t is ParseConfidenceTier => t != null);
  if (tiers.length === 0) return null;
  return tiers.reduce(
    (worst, t) => (TIER_RANK[t] < TIER_RANK[worst] ? t : worst),
    "high" as ParseConfidenceTier,
  );
}
