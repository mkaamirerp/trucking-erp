import { useCallback, useEffect, useState } from "react";
import {
  getPlatformAdminApiKey,
  platformAdminFetch,
  platformAdminJson,
  PlatformAdminHttpError,
  PlatformAdminUnauthorizedError,
} from "../lib/platformAdminFetch";
import { signalPlatformAdminUnauthorized } from "../components/PlatformShellLayout";
import {
  globalBrokerPromotionReasonOptions,
  globalBrokerPromotionReasonHint,
  globalBrokerPromotionTargets,
} from "../constants/globalBookingBrokerPromotionReasonCodes";
import {
  DUPLICATE_REVIEW_ACK_OPTIONS,
  DUPLICATE_REVIEW_DISMISS_OPTIONS,
  duplicateReviewReasonHint,
} from "../constants/globalBookingBrokerDuplicateReviewReasonCodes";
import { GlobalBookingBrokerMergeWizard } from "../components/GlobalBookingBrokerMergeWizard";

type GlobalBookingBrokerRow = {
  id: number;
  name: string;
  legal_name?: string | null;
  display_name?: string | null;
  mc_number?: string | null;
  dot_number?: string | null;
  cvor_number?: string | null;
  canonical_status: string;
  notes?: string | null;
  merged_into_global_broker_id?: number | null;
  merged_at?: string | null;
  created_at: string;
  updated_at: string;
};

type AuditEventRow = {
  id: number;
  global_broker_id: number;
  action: string;
  detail: Record<string, unknown> | null;
  created_at: string;
};

function formatDetailSummary(detail: Record<string, unknown> | null): string {
  if (!detail) return "—";
  const action = detail as {
    from?: string;
    to?: string;
    promotion_reason_hint?: string;
    promotion_reason_code?: string;
    note?: string;
    canonical_status?: string;
    name?: string;
  };
  if (typeof action.promotion_reason_hint === "string" && action.promotion_reason_hint) {
    const fr = typeof action.from === "string" ? action.from : "";
    const to = typeof action.to === "string" ? action.to : "";
    return `${fr} → ${to}: ${action.promotion_reason_hint}`;
  }
  if (typeof action.from === "string" && typeof action.to === "string") {
    const n = typeof action.note === "string" && action.note ? action.note : null;
    return `${action.from} → ${action.to}${n ? ` — ${n}` : " — legacy"}`;
  }
  if (typeof action.canonical_status === "string" && typeof action.name === "string") {
    return `Created (${action.canonical_status})`;
  }
  const dup = detail as {
    candidate_id?: unknown;
    duplicate_review_reason_hint?: string;
    review_status?: string;
  };
  if (
    dup.candidate_id != null &&
    typeof dup.duplicate_review_reason_hint === "string" &&
    dup.duplicate_review_reason_hint
  ) {
    const st = typeof dup.review_status === "string" ? dup.review_status : "";
    return `Duplicate review #${String(dup.candidate_id)} (${st}): ${dup.duplicate_review_reason_hint}`;
  }
  const prof = detail as { cvor_number?: { from?: string | null; to?: string | null } };
  if (prof.cvor_number && typeof prof.cvor_number === "object" && "from" in prof.cvor_number) {
    const fr = prof.cvor_number.from ?? "—";
    const to = prof.cvor_number.to ?? "—";
    return `CVOR: ${fr} → ${to}`;
  }
  return "Update";
}

function PromotionForm({
  broker,
  onDone,
}: {
  broker: GlobalBookingBrokerRow;
  onDone: () => void;
}) {
  const prev = broker.canonical_status;
  const targets = globalBrokerPromotionTargets(prev);
  const [target, setTarget] = useState<(typeof targets)[number]["value"] | "">(
    targets[0]?.value ?? "",
  );
  const reasonOpts = target ? globalBrokerPromotionReasonOptions(prev, target) : [];
  const [reason, setReason] = useState(reasonOpts[0]?.code ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const opts = target ? globalBrokerPromotionReasonOptions(prev, target) : [];
    setReason(opts[0]?.code ?? "");
    setErr(null);
  }, [target, prev]);

  const submit = async () => {
    if (!target || !reason) return;
    setBusy(true);
    setErr(null);
    try {
      const body: Record<string, unknown> = {
        canonical_status: target,
        promotion_reason_code: reason,
      };
      const t = note.trim();
      if (t) body.note = t;
      const res = await platformAdminFetch(`/platform/global-booking-brokers/${broker.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
          const j = JSON.parse(text) as { detail?: unknown };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          if (text) msg = text.slice(0, 200);
        }
        throw new PlatformAdminHttpError(msg, res.status, text);
      }
      onDone();
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      setErr(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  if (targets.length === 0) {
    return <span className="text-slate-500">Unknown status</span>;
  }

  return (
    <div className="flex flex-col gap-2 min-w-[220px]">
      {err ? <p className="text-xs text-red-400">{err}</p> : null}
      <label className="text-xs text-slate-500">
        Action
        <select
          className="mt-0.5 block w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
          value={target}
          onChange={(e) => setTarget(e.target.value as (typeof targets)[number]["value"])}
          disabled={busy}
        >
          {targets.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-slate-500">
        Reason
        <select
          className="mt-0.5 block w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={busy || reasonOpts.length === 0}
          title={globalBrokerPromotionReasonHint(reason) ?? undefined}
        >
          {reasonOpts.map((o) => (
            <option key={o.code} value={o.code}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-slate-500">
        Optional detail{" "}
        <span className="text-slate-600" title="Not shown as the primary reason; keep short">
          (tooltip / audit)
        </span>
        <textarea
          className="mt-0.5 block w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={busy}
          placeholder="Optional"
        />
      </label>
      <button
        type="button"
        onClick={() => void submit()}
        disabled={busy || !target || !reason}
        className="rounded border border-indigo-700 bg-indigo-950/50 px-2 py-1 text-xs text-indigo-200 hover:bg-indigo-900/50 disabled:opacity-50"
      >
        {busy ? "Saving…" : "Apply"}
      </button>
    </div>
  );
}

function BrokerCvorCell({ broker, onDone }: { broker: GlobalBookingBrokerRow; onDone: () => void }) {
  const [val, setVal] = useState(broker.cvor_number ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setVal(broker.cvor_number ?? "");
    setErr(null);
  }, [broker.id, broker.cvor_number]);

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const t = val.trim();
      const body: { cvor_number: string | null } = { cvor_number: t === "" ? null : t };
      const res = await platformAdminFetch(`/platform/global-booking-brokers/${broker.id}/profile`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
          const j = JSON.parse(text) as { detail?: unknown };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          if (text) msg = text.slice(0, 200);
        }
        throw new PlatformAdminHttpError(msg, res.status, text);
      }
      onDone();
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded border border-slate-800/80 bg-slate-950/40 p-2 space-y-1.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">CVOR (9 digits)</div>
      {err ? <p className="text-[11px] text-red-400">{err}</p> : null}
      <input
        type="text"
        inputMode="numeric"
        autoComplete="off"
        className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200 font-mono"
        placeholder="e.g. 123456789"
        value={val}
        onChange={(e) => setVal(e.target.value.replace(/\D/g, "").slice(0, 9))}
        disabled={busy}
      />
      <button
        type="button"
        onClick={() => void save()}
        disabled={busy}
        className="rounded border border-slate-600 px-2 py-0.5 text-[11px] text-slate-300 hover:bg-slate-800 disabled:opacity-50"
      >
        {busy ? "Saving…" : "Save CVOR"}
      </button>
    </div>
  );
}

type DupCandidateRow = {
  id: number;
  broker_low: {
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
  broker_high: DupCandidateRow["broker_low"];
  match_signals: string[];
  review_status: string;
  duplicate_review_reason_code: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
};

function dupOpenRowInvolvesMergeLoser(r: DupCandidateRow): boolean {
  return (
    r.review_status === "open" &&
    (r.broker_low.merged_into_global_broker_id != null ||
      r.broker_high.merged_into_global_broker_id != null)
  );
}

function formatDuplicateMatchSignal(sig: string): string {
  if (sig.startsWith("shared_cvor:")) {
    return `CVOR ${sig.slice("shared_cvor:".length)}`;
  }
  return sig;
}

function DupReviewForm({ row, onDone }: { row: DupCandidateRow; onDone: () => void }) {
  const [disposition, setDisposition] = useState<"dismissed" | "acknowledged">("dismissed");
  const [reason, setReason] = useState(DUPLICATE_REVIEW_DISMISS_OPTIONS[0]?.code ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const first =
      disposition === "dismissed"
        ? DUPLICATE_REVIEW_DISMISS_OPTIONS[0]?.code
        : DUPLICATE_REVIEW_ACK_OPTIONS[0]?.code;
    setReason(first ?? "");
  }, [disposition]);

  const submit = async () => {
    if (!reason) return;
    setBusy(true);
    setErr(null);
    try {
      const body: Record<string, unknown> = {
        review_status: disposition,
        duplicate_review_reason_code: reason,
      };
      const t = note.trim();
      if (t) body.note = t;
      const res = await platformAdminFetch(`/platform/global-booking-broker-duplicate-candidates/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
          const j = JSON.parse(text) as { detail?: unknown };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          if (text) msg = text.slice(0, 200);
        }
        throw new PlatformAdminHttpError(msg, res.status, text);
      }
      onDone();
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      setErr(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const reasonOpts =
    disposition === "dismissed" ? DUPLICATE_REVIEW_DISMISS_OPTIONS : DUPLICATE_REVIEW_ACK_OPTIONS;

  return (
    <div className="flex flex-col gap-2 min-w-[200px]">
      {err ? <p className="text-xs text-red-400">{err}</p> : null}
      <label className="text-xs text-slate-500">
        Disposition
        <select
          className="mt-0.5 block w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
          value={disposition}
          onChange={(e) => setDisposition(e.target.value as "dismissed" | "acknowledged")}
          disabled={busy}
        >
          <option value="dismissed">Dismiss (not duplicate)</option>
          <option value="acknowledged">Acknowledge (duplicate / manual follow-up)</option>
        </select>
      </label>
      <label className="text-xs text-slate-500">
        Reason
        <select
          className="mt-0.5 block w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={busy}
          title={duplicateReviewReasonHint(reason) ?? undefined}
        >
          {reasonOpts.map((o) => (
            <option key={o.code} value={o.code}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-slate-500">
        Optional note
        <textarea
          className="mt-0.5 block w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={busy}
        />
      </label>
      <button
        type="button"
        onClick={() => void submit()}
        disabled={busy || !reason}
        className="rounded border border-amber-900/60 bg-amber-950/30 px-2 py-1 text-xs text-amber-100 hover:bg-amber-900/20 disabled:opacity-50"
      >
        {busy ? "Saving…" : "Submit review"}
      </button>
    </div>
  );
}

function DuplicateCandidatesPanel() {
  const [dupFilter, setDupFilter] = useState<"open" | "all" | "dismissed" | "acknowledged">("open");
  const [dupRows, setDupRows] = useState<DupCandidateRow[] | null>(null);
  const [dupErr, setDupErr] = useState<string | null>(null);
  const [dupLoading, setDupLoading] = useState(true);
  const [scanBusy, setScanBusy] = useState(false);
  const [mergeWizardRow, setMergeWizardRow] = useState<DupCandidateRow | null>(null);

  const loadDup = useCallback(async () => {
    setDupErr(null);
    setDupLoading(true);
    if (!getPlatformAdminApiKey().trim()) {
      setDupRows(null);
      setDupLoading(false);
      return;
    }
    try {
      const qs =
        dupFilter === "all" ? "" : `?review_status=${encodeURIComponent(dupFilter)}`;
      const data = await platformAdminJson<DupCandidateRow[]>(
        `/platform/global-booking-broker-duplicate-candidates${qs}`,
      );
      setDupRows(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        setDupRows(null);
        setDupErr(null);
        return;
      }
      setDupRows(null);
      setDupErr(e instanceof Error ? e.message : "Failed to load duplicate candidates");
    } finally {
      setDupLoading(false);
    }
  }, [dupFilter]);

  useEffect(() => {
    void loadDup();
  }, [loadDup]);

  const runScan = async () => {
    setScanBusy(true);
    setDupErr(null);
    try {
      await platformAdminJson<{
        upserted_open: number;
        updated_open_signals: number;
        removed_stale_open: number;
        touched_dismissed_or_ack: number;
      }>("/platform/global-booking-broker-duplicate-candidates/refresh", { method: "POST" });
      await loadDup();
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      setDupErr(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanBusy(false);
    }
  };

  return (
    <section className="mt-8 rounded-lg border border-amber-900/40 bg-slate-900/40 p-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-amber-100/90">Possible duplicate pairs</h2>
          <p className="mt-1 text-xs text-slate-500">
            Scans shared MC/DOT, domains, known senders, and aliases. No automatic merges — mark candidates with
            structured reasons only. After you acknowledge a pair, use the merge wizard to preview and run a
            platform merge (operators only).
          </p>
        </div>
        <button
          type="button"
          onClick={() => void runScan()}
          disabled={scanBusy}
          className="text-sm rounded border border-amber-800 px-3 py-1 text-amber-100/90 hover:bg-amber-950/50 disabled:opacity-50 self-start"
        >
          {scanBusy ? "Scanning…" : "Scan / refresh pairs"}
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {(["open", "all", "dismissed", "acknowledged"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setDupFilter(f)}
            className={`rounded px-2.5 py-1 text-xs border ${
              dupFilter === f
                ? "border-amber-600 bg-amber-950/40 text-amber-100"
                : "border-slate-700 text-slate-400 hover:bg-slate-900/60"
            }`}
          >
            {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <button
          type="button"
          onClick={() => void loadDup()}
          disabled={dupLoading}
          className="rounded px-2.5 py-1 text-xs border border-slate-600 text-slate-400 hover:bg-slate-800 disabled:opacity-50"
        >
          Reload list
        </button>
      </div>

      {dupErr ? <p className="mt-3 text-sm text-red-400">{dupErr}</p> : null}
      {dupLoading ? <p className="mt-3 text-sm text-slate-400">Loading candidates…</p> : null}

      {!dupLoading && dupRows && dupRows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No rows for this filter. Run a scan if the list is empty.</p>
      ) : null}

      {!dupLoading && dupRows && dupRows.length > 0 ? (
        <div className="mt-4 overflow-x-auto rounded border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400 text-xs">
              <tr>
                <th className="px-3 py-2 font-medium">ID</th>
                <th className="px-3 py-2 font-medium">Pair</th>
                <th className="px-3 py-2 font-medium">Signals</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Review</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {dupRows.map((r) => (
                <tr key={r.id} className="align-top">
                  <td className="px-3 py-2 text-slate-400 font-mono text-xs">{r.id}</td>
                  <td className="px-3 py-2 text-slate-200 text-xs">
                    <div>
                      #{r.broker_low.id} {r.broker_low.display_name || r.broker_low.name}{" "}
                      <span className="text-slate-500">({r.broker_low.canonical_status})</span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      MC {r.broker_low.mc_number ?? "—"} · DOT {r.broker_low.dot_number ?? "—"} · CVOR{" "}
                      {r.broker_low.cvor_number ?? "—"}
                      {r.broker_low.merged_into_global_broker_id != null
                        ? ` · merged→#${r.broker_low.merged_into_global_broker_id}`
                        : ""}
                    </div>
                    <div className="text-slate-500">↔</div>
                    <div>
                      #{r.broker_high.id} {r.broker_high.display_name || r.broker_high.name}{" "}
                      <span className="text-slate-500">({r.broker_high.canonical_status})</span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      MC {r.broker_high.mc_number ?? "—"} · DOT {r.broker_high.dot_number ?? "—"} · CVOR{" "}
                      {r.broker_high.cvor_number ?? "—"}
                      {r.broker_high.merged_into_global_broker_id != null
                        ? ` · merged→#${r.broker_high.merged_into_global_broker_id}`
                        : ""}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-400 max-w-xs">
                    <span
                      title={r.match_signals.map(formatDuplicateMatchSignal).join(", ")}
                      className="line-clamp-3"
                    >
                      {r.match_signals.map(formatDuplicateMatchSignal).join(", ")}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-300 text-xs capitalize">{r.review_status}</td>
                  <td className="px-3 py-2">
                    {r.review_status === "open" && dupOpenRowInvolvesMergeLoser(r) ? (
                      <div className="flex flex-col gap-1.5 text-xs text-slate-400 min-w-[200px]">
                        <p className="text-amber-100/90 font-medium">Handled — merge already recorded</p>
                        <p className="text-[11px] text-slate-500 leading-snug">
                          One side is merged into another broker (see merged→ above). This row is not actionable. Run
                          &quot;Scan / refresh pairs&quot; to drop it from the open queue.
                        </p>
                      </div>
                    ) : r.review_status === "open" ? (
                      <DupReviewForm row={r} onDone={() => void loadDup()} />
                    ) : (
                      <div className="flex flex-col gap-2 text-xs text-slate-500 min-w-[200px]">
                        {r.duplicate_review_reason_code ? (
                          <span title={r.note ?? undefined}>
                            {duplicateReviewReasonHint(r.duplicate_review_reason_code) || r.duplicate_review_reason_code}
                          </span>
                        ) : (
                          "—"
                        )}
                        {r.review_status === "acknowledged" ? (
                          <button
                            type="button"
                            onClick={() => setMergeWizardRow(r)}
                            className="rounded border border-emerald-900/60 bg-emerald-950/25 px-2 py-1 text-left text-[11px] text-emerald-100/90 hover:bg-emerald-900/25 w-full"
                          >
                            Open merge wizard
                          </button>
                        ) : (
                          <p className="text-[11px] text-slate-600 leading-snug">
                            Merge wizard only runs for pairs in <strong className="text-slate-500">Acknowledged</strong> status
                            (not dismissed). Use the Open filter, acknowledge the duplicate, then return here.
                          </p>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {mergeWizardRow ? (
        <GlobalBookingBrokerMergeWizard
          row={mergeWizardRow}
          onClose={() => setMergeWizardRow(null)}
          onDone={() => void loadDup()}
        />
      ) : null}
    </section>
  );
}

function AuditDrawer({ brokerId }: { brokerId: number }) {
  const [rows, setRows] = useState<AuditEventRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const data = await platformAdminJson<AuditEventRow[]>(
        `/platform/global-booking-brokers/${brokerId}/audit-events?limit=30`,
      );
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        setRows(null);
        return;
      }
      setRows(null);
      setErr(e instanceof Error ? e.message : "Failed to load audit");
    } finally {
      setLoading(false);
    }
  }, [brokerId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <p className="text-xs text-slate-500 py-2">Loading audit…</p>;
  if (err) return <p className="text-xs text-red-400 py-2">{err}</p>;
  if (!rows?.length) return <p className="text-xs text-slate-500 py-2">No audit events.</p>;

  return (
    <ul className="text-xs text-slate-400 space-y-2 py-2 border-t border-slate-800 mt-2">
      {rows.map((r) => (
        <li key={r.id} className="font-mono text-[11px] leading-snug">
          <span className="text-slate-500">
            {new Date(r.created_at).toISOString().replace("T", " ").slice(0, 19)}Z
          </span>{" "}
          <span className="text-slate-300">{r.action}</span>
          <div className="text-slate-400 mt-0.5">{formatDetailSummary(r.detail)}</div>
          {r.detail && Object.keys(r.detail).length > 0 ? (
            <details className="mt-1 text-slate-500">
              <summary className="cursor-pointer text-slate-500 hover:text-slate-400">Raw detail</summary>
              <pre className="mt-1 whitespace-pre-wrap break-all text-[10px] text-slate-500">
                {JSON.stringify(r.detail, null, 2)}
              </pre>
            </details>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export default function PlatformGlobalBookingBrokersPage() {
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("pending");
  const [rows, setRows] = useState<GlobalBookingBrokerRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    if (!getPlatformAdminApiKey().trim()) {
      setRows(null);
      setLoading(false);
      return;
    }
    try {
      const qs = filter === "all" ? "" : `?canonical_status=${encodeURIComponent(filter)}`;
      const data = await platformAdminJson<GlobalBookingBrokerRow[]>(`/platform/global-booking-brokers${qs}`);
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        setRows(null);
        setError(null);
        return;
      }
      setRows(null);
      setError(e instanceof Error ? e.message : "Failed to load brokers");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-white tracking-tight">Global booking brokers</h1>
          <p className="mt-1 text-sm text-slate-400">
            Promotion queue for platform reference brokers (approved rows are intake-eligible). Reasons are structured
            codes; optional note is supplemental only. Duplicate detection is candidate-only — operators review.
            Acknowledged pairs can use the merge wizard (preview + execute); there is no automatic merge.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="text-sm rounded border border-slate-600 px-3 py-1 text-slate-300 hover:bg-slate-800 disabled:opacity-50 self-start"
        >
          Refresh
        </button>
      </div>

      <DuplicateCandidatesPanel />

      <h2 className="text-sm font-medium text-slate-300 mt-10">Brokers</h2>
      <div className="mt-2 flex flex-wrap gap-2">
        {(["all", "pending", "approved", "rejected"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`rounded px-3 py-1 text-sm border ${
              filter === f
                ? "border-indigo-500 bg-indigo-950/40 text-indigo-200"
                : "border-slate-700 text-slate-400 hover:bg-slate-900/60"
            }`}
          >
            {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}

      {loading ? <p className="mt-6 text-sm text-slate-400">Loading…</p> : null}

      {!loading && rows && rows.length === 0 ? (
        <p className="mt-6 text-sm text-slate-400">No brokers for this filter.</p>
      ) : null}

      {!loading && rows && rows.length > 0 ? (
        <div className="mt-6 overflow-x-auto rounded-lg border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-3 py-2 font-medium">ID</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">MC / DOT</th>
                <th className="px-3 py-2 font-medium">CVOR</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Promotion</th>
                <th className="px-3 py-2 font-medium">Audit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.map((b) => (
                <tr key={b.id} className="hover:bg-slate-900/40 align-top">
                  <td className="px-3 py-2 text-slate-300">{b.id}</td>
                  <td className="px-3 py-2 text-slate-200">
                    <div>{b.display_name || b.name}</div>
                    {b.merged_into_global_broker_id != null ? (
                      <div className="text-[11px] text-amber-200/90 mt-1 font-mono">
                        Merged into #{b.merged_into_global_broker_id}
                        {b.merged_at
                          ? ` · ${b.merged_at.replace("T", " ").slice(0, 19)}Z`
                          : null}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-slate-400 text-xs">
                    {[b.mc_number, b.dot_number].filter(Boolean).join(" / ") || "—"}
                  </td>
                  <td className="px-3 py-2 text-slate-400 text-xs align-top">
                    <span className="font-mono">{b.cvor_number ?? "—"}</span>
                    <BrokerCvorCell broker={b} onDone={() => void load()} />
                  </td>
                  <td className="px-3 py-2 text-slate-300 capitalize">{b.canonical_status}</td>
                  <td className="px-3 py-2">
                    <PromotionForm
                      key={`${b.id}-${b.canonical_status}`}
                      broker={b}
                      onDone={() => void load()}
                    />
                  </td>
                  <td className="px-3 py-2">
                    {expanded === b.id ? (
                      <div>
                        <AuditDrawer brokerId={b.id} />
                        <button
                          type="button"
                          className="mt-1 text-xs text-slate-500 hover:text-slate-400"
                          onClick={() => setExpanded(null)}
                        >
                          Hide
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="text-xs text-indigo-400 hover:text-indigo-300"
                        onClick={() => setExpanded(b.id)}
                      >
                        Show
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
