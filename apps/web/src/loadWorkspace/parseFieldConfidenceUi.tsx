import type { ReactNode } from "react";
import type { LoadDocumentParseExtracted } from "@/api";
import type { ParseScalarFieldKey } from "@/loadWorkspace/loadParseHydrationState";
import { VISIBLE_BROKER_LOAD_REFERENCE_LABEL } from "@/loadWorkspace/loadOperationalReferences";

export type ParseConfidenceTier = "high" | "medium" | "low";

/** Document-level RC review band (includes neutral when confidence is unavailable). */
export type DocumentReviewTier = ParseConfidenceTier | "neutral";

const TIER_RANK: Record<ParseConfidenceTier, number> = { low: 0, medium: 1, high: 2 };

export function normalizeConfidenceValue(raw: string | null | undefined): ParseConfidenceTier | null {
  const l = (raw ?? "").trim().toLowerCase();
  if (l === "high") return "high";
  if (l === "medium" || l === "med") return "medium";
  if (l === "low") return "low";
  return null;
}

export const CRITICAL_FIELD_CONFIDENCE_KEYS = [
  "broker_name_snapshot",
  "broker_load_reference",
  "rate",
  "stops",
] as const;

export type CriticalFieldConfidenceKey = (typeof CRITICAL_FIELD_CONFIDENCE_KEYS)[number];

export const PARSE_SCALAR_TO_CONFIDENCE_KEY: Record<ParseScalarFieldKey, string> = {
  brokerNameSnapshot: "broker_name_snapshot",
  brokerLoadReference: "broker_load_reference",
  freightMode: "mode",
  equipmentType: "equipment_type",
  trailerType: "trailer_type",
  trailerSize: "trailer_size",
  commodity: "commodity",
  estimatedWeight: "estimated_weight",
  temperatureRequirement: "temperature_requirement",
  rate: "rate",
  customerRate: "customer_rate",
  miles: "miles",
};

const CRITICAL_WARNING_PREFIXES = [
  "invalid_stop_type:",
  "invalid_stop_sequence:",
  "duplicate_stop_sequence:",
  "invalid_date:",
  "value_not_found_in_source: broker_load_reference",
  "value_not_found_in_source: rate",
] as const;

export type ParseWarningReviewClass = "critical" | "review" | null;

export function classifyParseWarningsForReview(
  warnings?: string[] | null,
): ParseWarningReviewClass {
  if (!warnings?.length) return null;
  for (const w of warnings) {
    const t = w.trim();
    if (CRITICAL_WARNING_PREFIXES.some((p) => t.startsWith(p))) return "critical";
  }
  return "review";
}

function criticalFieldIsPresent(ex: LoadDocumentParseExtracted, key: CriticalFieldConfidenceKey): boolean {
  switch (key) {
    case "broker_name_snapshot":
      return Boolean((ex.broker_name_snapshot ?? "").trim());
    case "broker_load_reference":
      return Boolean((ex.broker_load_reference ?? "").trim());
    case "rate":
      return ex.rate != null && Number.isFinite(Number(ex.rate));
    case "stops":
      return Array.isArray(ex.stops) && ex.stops.length > 0;
    default:
      return false;
  }
}

function hasAnyRatedConfidence(fieldConfidence: Record<string, string>): boolean {
  return Object.values(fieldConfidence).some((v) => normalizeConfidenceValue(v) != null);
}

/**
 * RC document review tier — separate from per-field accents.
 * Green only when every in-play critical field is rated high; missing ratings → review (amber).
 */
export function computeDocumentReviewTier(
  extracted: LoadDocumentParseExtracted | null | undefined,
  fieldConfidence: Record<string, string> | null | undefined,
  warnings?: string[] | null,
): DocumentReviewTier {
  const fc = fieldConfidence ?? {};
  const ex = extracted ?? ({ references: [], stops: [] } as LoadDocumentParseExtracted);
  const warningClass = classifyParseWarningsForReview(warnings);
  const hasConfidence = hasAnyRatedConfidence(fc);

  const criticalInPlay = CRITICAL_FIELD_CONFIDENCE_KEYS.filter((k) => criticalFieldIsPresent(ex, k));

  if (!hasConfidence && criticalInPlay.length === 0) {
    return warningClass ? "medium" : "neutral";
  }

  if (warningClass === "critical") {
    return "low";
  }

  const keysToJudge =
    criticalInPlay.length > 0 ? criticalInPlay : [...CRITICAL_FIELD_CONFIDENCE_KEYS];

  const tiers = keysToJudge.map((k) => normalizeConfidenceValue(fc[k]));
  const missingRating = tiers.some((t) => t == null);
  const hasLow = tiers.some((t) => t === "low");
  const hasMedium = tiers.some((t) => t === "medium");

  if (hasLow) return "low";
  if (warningClass === "review") return "medium";
  if (hasMedium || missingRating) return "medium";
  if (tiers.length > 0 && tiers.every((t) => t === "high")) return "high";
  if (!hasConfidence) return "neutral";
  return "medium";
}

/** @deprecated Use computeDocumentReviewTier — kept for tests migrating off worst-tier-only logic. */
export function worstParseConfidenceTier(
  fieldConfidence: Record<string, string> | null | undefined,
  parseWarnings?: string[] | null,
): ParseConfidenceTier {
  const tier = computeDocumentReviewTier(null, fieldConfidence, parseWarnings);
  if (tier === "neutral") return "medium";
  return tier;
}

export function documentReviewTierLabel(tier: DocumentReviewTier): string {
  switch (tier) {
    case "high":
      return "High confidence";
    case "medium":
      return "Review needed";
    case "low":
      return "Check PDF";
    case "neutral":
      return "Not rated";
  }
}

export function parseConfidenceTierLabel(tier: ParseConfidenceTier): string {
  return documentReviewTierLabel(tier);
}

export function parseConfidenceRcPanelClasses(tier: DocumentReviewTier): {
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
    case "neutral":
      return {
        border: "border-[var(--trk-border)]",
        badge: "border border-[var(--trk-border)] bg-[var(--trk-surface-2)] text-[var(--trk-text-muted)]",
        title: "text-[var(--trk-text-muted)]",
      };
  }
}

export function parseConfidenceAppliedChipClasses(
  tier: ParseConfidenceTier | DocumentReviewTier | null,
): string {
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

const TIER_DOT: Record<ParseConfidenceTier, string> = {
  high: "bg-emerald-500",
  medium: "bg-amber-500",
  low: "bg-red-500",
};

const TIER_ACCENT: Record<ParseConfidenceTier, string> = {
  high: "bg-emerald-500/80",
  medium: "bg-amber-500/80",
  low: "bg-red-500/80",
};

export function confidenceTierForFieldKey(
  confidenceKey: string | null | undefined,
  fieldConfidence: Record<string, string> | null | undefined,
  manualOverride?: boolean,
): ParseConfidenceTier | null {
  if (manualOverride) return null;
  const key = (confidenceKey ?? "").trim();
  if (!key) return null;
  return normalizeConfidenceValue(fieldConfidence?.[key]);
}

export function confidenceTierForScalarField(
  scalarKey: ParseScalarFieldKey,
  fieldConfidence: Record<string, string> | null | undefined,
  manualOverrideKeys?: Set<ParseScalarFieldKey>,
): ParseConfidenceTier | null {
  const manual = manualOverrideKeys?.has(scalarKey) ?? false;
  return confidenceTierForFieldKey(PARSE_SCALAR_TO_CONFIDENCE_KEY[scalarKey], fieldConfidence, manual);
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

type ParseConfidenceFieldProps = {
  label: ReactNode;
  confidenceKey?: string | null;
  fieldConfidence?: Record<string, string> | null;
  manualOverride?: boolean;
  labelClassName?: string;
  className?: string;
  children: ReactNode;
};

/** Label dot + partial L-shaped accent on the control (not a full rectangle). */
export function ParseConfidenceField({
  label,
  confidenceKey,
  fieldConfidence,
  manualOverride,
  labelClassName,
  className,
  children,
}: ParseConfidenceFieldProps) {
  const tier = confidenceTierForFieldKey(confidenceKey, fieldConfidence, manualOverride);
  const hasLabel = label !== null && label !== undefined && label !== "";
  return (
    <div className={className}>
      {hasLabel ? (
        <label className={`${labelClassName ?? ""} flex items-center gap-1.5`}>
          {tier ? (
            <span
              className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${TIER_DOT[tier]}`}
              title={`AI extraction: ${parseConfidenceTierLabel(tier)}`}
              aria-hidden
            />
          ) : null}
          <span className="min-w-0">{label}</span>
        </label>
      ) : null}
      <div className={`relative ${hasLabel ? "mt-0" : ""}`}>
        {tier ? (
          <>
            <span
              className={`pointer-events-none absolute bottom-0 left-0 top-0 z-[1] w-0.5 rounded-l ${TIER_ACCENT[tier]}`}
              aria-hidden
            />
            <span
              className={`pointer-events-none absolute left-0 top-0 z-[1] h-0.5 w-[38%] max-w-[5.5rem] ${TIER_ACCENT[tier]}`}
              aria-hidden
            />
            <span
              className={`pointer-events-none absolute bottom-0 left-0 z-[1] h-0.5 w-[38%] max-w-[5.5rem] ${TIER_ACCENT[tier]}`}
              aria-hidden
            />
          </>
        ) : null}
        <div className="relative z-0 [&_input]:focus:relative [&_select]:focus:relative [&_textarea]:focus:relative">
          {children}
        </div>
      </div>
    </div>
  );
}
