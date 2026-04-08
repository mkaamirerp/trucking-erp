import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import {
  friendlyMergeErrorMessage,
  mergeExecuteStatusLabel,
  mergeResolutionFieldLabel,
  parseDetailFromErrorBody,
} from "../lib/globalBookingBrokerMergeErrors";
import {
  getPlatformAdminApiKey,
  platformAdminFetch,
  PlatformAdminHttpError,
  PlatformAdminUnauthorizedError,
} from "../lib/platformAdminFetch";
import { signalPlatformAdminUnauthorized } from "./PlatformShellLayout";

export type MergeWizardBrokerMini = {
  id: number;
  name: string;
  display_name: string | null;
  canonical_status: string;
  mc_number: string | null;
  dot_number: string | null;
  cvor_number?: string | null;
  merged_into_global_broker_id?: number | null;
  merged_at?: string | null;
};

export type MergeWizardDupRow = {
  id: number;
  broker_low: MergeWizardBrokerMini;
  broker_high: MergeWizardBrokerMini;
  review_status: string;
};

type FieldComparison = {
  field: string;
  kind: string;
  classification: string;
  source_normalized: string | null;
  survivor_normalized: string | null;
};

type PreviewSummary = {
  has_blockers: boolean;
  has_blocking_conflict: boolean;
  blocking_conflict_fields: string[];
  operator_choice_required_fields: string[];
  safe_default_fields: string[];
  persist_eligible: boolean;
};

type PreviewBody = {
  schema_version: number;
  source_global_broker_id: number;
  survivor_global_broker_id: number;
  duplicate_candidate_id: number | null;
  source_snapshot: Record<string, unknown>;
  survivor_snapshot: Record<string, unknown>;
  blockers: { code: string; detail?: Record<string, unknown> }[];
  field_comparisons: FieldComparison[];
  summary: PreviewSummary;
};

type MergePreviewResponse = {
  preview_id: number | null;
  preview_hash: string;
  preview: PreviewBody;
};

type MergeExecuteResponse = {
  status: "completed" | "already_completed";
  preview_id: number;
  preview_hash: string;
  source_global_broker_id: number;
  survivor_global_broker_id: number;
  duplicate_candidate_id: number | null;
  child_stats: Record<string, number> | null;
};

function formatMerged(blurb: string | null | undefined): string | null {
  if (!blurb || !blurb.trim()) return null;
  try {
    const d = new Date(blurb);
    if (!Number.isNaN(d.getTime())) return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    /* ignore */
  }
  return blurb;
}

function MergedBanner({ label, mergedInto, mergedAt }: { label: string; mergedInto: number | null | undefined; mergedAt?: string | null }) {
  if (mergedInto == null) return null;
  const when = formatMerged(mergedAt ?? null);
  return (
    <div className="rounded border border-amber-700/50 bg-amber-950/30 px-2 py-1.5 text-[11px] text-amber-100/90">
      <span className="font-medium">{label}:</span> already merged into broker #{mergedInto}
      {when ? ` · ${when}` : null}.
    </div>
  );
}

function classificationLabel(c: string): { text: string; tone: "bad" | "warn" | "info" | "ok" } {
  switch (c) {
    case "blocking_conflict":
      return { text: "Blocks merge", tone: "bad" };
    case "operator_choice_required":
      return { text: "Your choice needed", tone: "warn" };
    case "safe_default":
      return { text: "Will fill in automatically", tone: "info" };
    case "aligned":
      return { text: "No action needed", tone: "ok" };
    default:
      return { text: c, tone: "info" };
  }
}

function RegulatoryBlock({ comparisons }: { comparisons: FieldComparison[] }) {
  const regs = comparisons.filter((x) => x.kind === "regulatory");
  const label: Record<string, string> = {
    mc_number: "MC number",
    dot_number: "USDOT",
    cvor_number: "CVOR",
  };
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-950/60 p-3">
      <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wide">Regulatory IDs (MC / USDOT / CVOR)</h4>
      <p className="text-[11px] text-slate-500 mt-1">
        These must not contradict each other when both sides are filled in. If one side is empty, the survivor will usually receive the value from the other.
      </p>
      <ul className="mt-2 space-y-2">
        {regs.map((r) => {
          const { text, tone } = classificationLabel(r.classification);
          const toneCls =
            tone === "bad"
              ? "border-red-800/60 bg-red-950/25 text-red-100/90"
              : tone === "warn"
                ? "border-amber-800/50 bg-amber-950/20 text-amber-100/80"
                : tone === "ok"
                  ? "border-slate-700 text-slate-400"
                  : "border-slate-700 text-slate-300";
          return (
            <li key={r.field} className={`rounded border px-2 py-1.5 text-xs ${toneCls}`}>
              <div className="font-medium">{label[r.field] ?? r.field}</div>
              <div className="font-mono text-[11px] mt-0.5 opacity-90">
                Retiring: {r.source_normalized ?? "—"} · Keeping: {r.survivor_normalized ?? "—"}
              </div>
              <div className="text-[10px] mt-1 uppercase tracking-wide opacity-80">{text}</div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function NameConflicts({
  comparisons,
  choice,
  setChoice,
}: {
  comparisons: FieldComparison[];
  choice: Partial<Record<"name" | "legal_name" | "display_name", "source" | "survivor">>;
  setChoice: Dispatch<
    SetStateAction<Partial<Record<"name" | "legal_name" | "display_name", "source" | "survivor">>>
  >;
}) {
  const names = comparisons.filter((x) => x.kind === "parent_name" && x.classification === "operator_choice_required");
  if (names.length === 0) return null;
  return (
    <div className="rounded-lg border border-amber-900/40 bg-amber-950/15 p-3 mt-3">
      <h4 className="text-xs font-semibold text-amber-100/90">Name fields — choose what to keep</h4>
      <p className="text-[11px] text-slate-500 mt-1">Pick whether the surviving record keeps the value from the retiring record or its own current value.</p>
      <ul className="mt-2 space-y-3">
        {names.map((r) => (
          <li key={r.field} className="text-xs">
            <div className="text-slate-300 font-medium capitalize">{mergeResolutionFieldLabel(r.field)}</div>
            <div className="text-[11px] text-slate-500 mt-0.5 font-mono">
              Retiring: {String(r.source_normalized ?? "—")} · Keeping: {String(r.survivor_normalized ?? "—")}
            </div>
            <div className="flex gap-3 mt-1">
              <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                <input
                  type="radio"
                  name={`res-${r.field}`}
                  checked={choice[r.field as "name" | "legal_name" | "display_name"] === "source"}
                  onChange={() =>
                    setChoice((s) => ({
                      ...s,
                      [r.field]: "source",
                    }))
                  }
                />
                Use retiring record
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                <input
                  type="radio"
                  name={`res-${r.field}`}
                  checked={choice[r.field as "name" | "legal_name" | "display_name"] === "survivor"}
                  onChange={() =>
                    setChoice((s) => ({
                      ...s,
                      [r.field]: "survivor",
                    }))
                  }
                />
                Use keeping record
              </label>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function GlobalBookingBrokerMergeWizard({
  row,
  onClose,
  onDone,
}: {
  row: MergeWizardDupRow;
  onClose: () => void;
  onDone: () => void;
}) {
  const [survivorIsLow, setSurvivorIsLow] = useState(true);
  const sourceId = survivorIsLow ? row.broker_high.id : row.broker_low.id;
  const survivorId = survivorIsLow ? row.broker_low.id : row.broker_high.id;
  const sourceBroker = survivorIsLow ? row.broker_high : row.broker_low;
  const survivorBroker = survivorIsLow ? row.broker_low : row.broker_high;

  const [previewBusy, setPreviewBusy] = useState(false);
  const [executeBusy, setExecuteBusy] = useState(false);
  const [previewOut, setPreviewOut] = useState<MergePreviewResponse | null>(null);
  const [choice, setChoice] = useState<
    Partial<Record<"name" | "legal_name" | "display_name", "source" | "survivor">>
  >({});
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState<MergeExecuteResponse | null>(null);

  useEffect(() => {
    setPreviewOut(null);
    setSuccess(null);
    setErr(null);
    setChoice({});
  }, [survivorIsLow, sourceId, survivorId]);

  const canExecute = useMemo(() => {
    if (!previewOut?.preview_id) return false;
    const p = previewOut.preview;
    if (p.summary.has_blockers || p.summary.has_blocking_conflict || !p.summary.persist_eligible) return false;
    const needed = p.summary.operator_choice_required_fields ?? [];
    for (const f of needed) {
      if (f !== "name" && f !== "legal_name" && f !== "display_name") continue;
      if (!choice[f]) return false;
    }
    return true;
  }, [previewOut, choice]);

  const runPreview = useCallback(async () => {
    if (!getPlatformAdminApiKey().trim()) return;
    setPreviewBusy(true);
    setErr(null);
    setSuccess(null);
    setPreviewOut(null);
    setChoice({});
    try {
      const res = await platformAdminFetch("/platform/global-booking-brokers/merge/preview", {
        method: "POST",
        body: JSON.stringify({
          source_global_broker_id: sourceId,
          survivor_global_broker_id: survivorId,
          duplicate_candidate_id: row.id,
        }),
      });
      const text = await res.text();
      if (!res.ok) {
        const raw = parseDetailFromErrorBody(text, `HTTP ${res.status}`);
        throw new PlatformAdminHttpError(friendlyMergeErrorMessage(raw), res.status, text);
      }
      setPreviewOut(JSON.parse(text) as MergePreviewResponse);
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      setErr(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setPreviewBusy(false);
    }
  }, [sourceId, survivorId, row.id]);

  const runExecute = useCallback(async () => {
    if (!previewOut?.preview_id) return;
    setExecuteBusy(true);
    setErr(null);
    try {
      const body: Record<string, unknown> = {
        preview_id: previewOut.preview_id,
        preview_hash: previewOut.preview_hash,
      };
      if (choice.name) body.name_resolution = choice.name;
      if (choice.legal_name) body.legal_name_resolution = choice.legal_name;
      if (choice.display_name) body.display_name_resolution = choice.display_name;
      const res = await platformAdminFetch("/platform/global-booking-brokers/merge/execute", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) {
        const raw = parseDetailFromErrorBody(text, `HTTP ${res.status}`);
        throw new PlatformAdminHttpError(friendlyMergeErrorMessage(raw), res.status, text);
      }
      const out = JSON.parse(text) as MergeExecuteResponse;
      setSuccess(out);
      onDone();
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      setErr(e instanceof Error ? e.message : "Execute failed");
    } finally {
      setExecuteBusy(false);
    }
  }, [previewOut, choice, onDone]);

  const p = previewOut?.preview;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-wizard-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-center justify-between gap-2 border-b border-slate-800 bg-slate-900/95 px-4 py-3 backdrop-blur">
          <h2 id="merge-wizard-title" className="text-base font-semibold text-white">
            Merge duplicate brokers
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            Close
          </button>
        </div>

        <div className="p-4 space-y-4 text-sm text-slate-300">
          <p className="text-xs text-slate-500">
            Candidate #{row.id} (acknowledged). Choose which record stays active. The other is retired: active domains, known senders, and aliases move to the survivor when they don’t already exist there.
          </p>

          <MergedBanner label="Retiring record" mergedInto={sourceBroker.merged_into_global_broker_id} mergedAt={sourceBroker.merged_at} />
          <MergedBanner label="Keeping record" mergedInto={survivorBroker.merged_into_global_broker_id} mergedAt={survivorBroker.merged_at} />

          <fieldset className="space-y-2">
            <legend className="text-xs font-medium text-slate-400">Record to keep (survivor)</legend>
            <label className="flex items-start gap-2 cursor-pointer rounded border border-slate-800 p-2 hover:bg-slate-950/80">
              <input type="radio" name="survivor" checked={survivorIsLow} onChange={() => setSurvivorIsLow(true)} />
              <span>
                <span className="font-mono text-indigo-300">#{row.broker_low.id}</span>{" "}
                {row.broker_low.display_name || row.broker_low.name}{" "}
                <span className="text-slate-500">({row.broker_low.canonical_status})</span>
              </span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer rounded border border-slate-800 p-2 hover:bg-slate-950/80">
              <input type="radio" name="survivor" checked={!survivorIsLow} onChange={() => setSurvivorIsLow(false)} />
              <span>
                <span className="font-mono text-indigo-300">#{row.broker_high.id}</span>{" "}
                {row.broker_high.display_name || row.broker_high.name}{" "}
                <span className="text-slate-500">({row.broker_high.canonical_status})</span>
              </span>
            </label>
          </fieldset>

          <div className="text-xs text-slate-500 rounded bg-slate-950/50 px-2 py-1.5 border border-slate-800">
            Retiring: <span className="font-mono text-slate-400">#{sourceId}</span> · Keeping:{" "}
            <span className="font-mono text-slate-400">#{survivorId}</span>
          </div>

          <button
            type="button"
            onClick={() => void runPreview()}
            disabled={previewBusy || !!success}
            className="w-full rounded border border-indigo-600 bg-indigo-950/40 py-2 text-sm font-medium text-indigo-100 hover:bg-indigo-900/30 disabled:opacity-50"
          >
            {previewBusy ? "Running preview…" : "Run preview"}
          </button>

          {err ? <p className="text-sm text-red-400">{err}</p> : null}

          {success ? (
            <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/25 p-3 text-emerald-100/90">
              <p className="font-medium">{mergeExecuteStatusLabel(success.status)}</p>
              <ul className="mt-2 text-xs text-emerald-200/80 space-y-1 font-mono">
                <li>Preview #{success.preview_id}</li>
                <li>Hash {success.preview_hash.slice(0, 12)}…</li>
                <li>
                  Retired #{success.source_global_broker_id} → kept #{success.survivor_global_broker_id}
                </li>
                {success.duplicate_candidate_id != null ? <li>Duplicate candidate #{success.duplicate_candidate_id}</li> : null}
              </ul>
              {success.child_stats && success.status === "completed" ? (
                <div className="mt-2 text-[11px] text-slate-400 border-t border-emerald-900/40 pt-2">
                  <span className="text-slate-500">Child rows:</span> domains +{success.child_stats.domains_rehomed ?? 0}{" "}
                  / −{success.child_stats.domains_deactivated ?? 0}, senders +{success.child_stats.senders_rehomed ?? 0} / −
                  {success.child_stats.senders_deactivated ?? 0}, aliases +{success.child_stats.aliases_rehomed ?? 0} / −
                  {success.child_stats.aliases_deactivated ?? 0}
                </div>
              ) : null}
              <button
                type="button"
                onClick={onClose}
                className="mt-3 rounded border border-emerald-800 px-3 py-1 text-xs text-emerald-100 hover:bg-emerald-900/30"
              >
                Done
              </button>
            </div>
          ) : null}

          {p && !success ? (
            <div className="space-y-3 border-t border-slate-800 pt-3">
              {p.blockers.length > 0 ? (
                <div className="rounded-lg border border-red-800/50 bg-red-950/20 p-3">
                  <h3 className="text-xs font-semibold text-red-200 uppercase tracking-wide">Cannot merge</h3>
                  <ul className="mt-2 list-disc list-inside text-xs text-red-100/85 space-y-1">
                    {p.blockers.map((b) => (
                      <li key={b.code}>{friendlyMergeErrorMessage(b.code)}</li>
                    ))}
                  </ul>
                  {!p.summary.persist_eligible ? (
                    <p className="mt-2 text-[11px] text-red-200/70">No saved preview token — execute stays disabled until these are cleared.</p>
                  ) : null}
                </div>
              ) : null}

              {p.summary.has_blocking_conflict && p.blockers.length === 0 ? (
                <div className="rounded-lg border border-red-800/50 bg-red-950/20 p-3">
                  <h3 className="text-xs font-semibold text-red-200">Regulatory conflict</h3>
                  <p className="text-xs text-red-100/80 mt-1">{friendlyMergeErrorMessage("merge_regulatory_blocking_conflict")}</p>
                  <p className="text-[11px] text-red-200/60 mt-1">Fields: {(p.summary.blocking_conflict_fields ?? []).join(", ") || "—"}</p>
                </div>
              ) : null}

              {!p.summary.has_blockers && !p.summary.has_blocking_conflict && p.summary.persist_eligible && previewOut.preview_id ? (
                <p className="text-xs text-emerald-200/80 rounded border border-emerald-900/40 bg-emerald-950/15 px-2 py-1.5">
                  Preview saved — you can run merge if name choices (if any) are complete.
                </p>
              ) : null}

              {!p.summary.persist_eligible && p.blockers.length === 0 ? (
                <p className="text-xs text-amber-200/80">{friendlyMergeErrorMessage("merge_preview_not_eligible")}</p>
              ) : null}

              <RegulatoryBlock comparisons={p.field_comparisons} />

              {p.field_comparisons.some(
                (x) => x.kind === "parent_name" && (x.classification === "operator_choice_required" || x.classification === "safe_default"),
              ) ? (
                <div className="text-[11px] text-slate-500">
                  Other name fields: aligned or will copy automatically where one side is empty.
                </div>
              ) : null}

              <NameConflicts comparisons={p.field_comparisons} choice={choice} setChoice={setChoice} />

              <button
                type="button"
                onClick={() => void runExecute()}
                disabled={executeBusy || !canExecute || !!success}
                className="w-full rounded border border-emerald-700 bg-emerald-950/30 py-2 text-sm font-medium text-emerald-100 hover:bg-emerald-900/25 disabled:opacity-50"
              >
                {executeBusy ? "Merging…" : "Execute merge"}
              </button>
              {!canExecute && previewOut.preview_id && p.summary.persist_eligible && !p.summary.has_blockers ? (
                <p className="text-[11px] text-slate-500">Select all required name choices above to enable merge.</p>
              ) : null}
              {!previewOut.preview_id ? (
                <p className="text-[11px] text-slate-500">Execute is only available after a successful preview with no blockers and no regulatory conflict.</p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
