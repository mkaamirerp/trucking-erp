import { useCallback, useEffect, useMemo, useState } from "react";
import {
  classifyFuelReasonGroup,
  getFuelBvdCanonicalTransactions,
  getFuelBvdClassificationAudit,
  getFuelBvdClassificationSummary,
  getFuelBvdUnresolvedClassificationGroups,
  getFuelChargeCategories,
  setFuelTransactionClassification,
  type FuelCanonicalTransaction,
  type FuelChargeCategory,
  type FuelClassificationAuditEvent,
  type FuelClassificationSummary,
  type FuelUnresolvedReasonGroup,
} from "../../api";

type Props = {
  importId: string;
  canManage: boolean;
};

function classificationSourceLabel(source: string | null | undefined): string {
  if (!source) return "—";
  if (source === "TENANT_MAPPING") return "Tenant mapping";
  if (source === "PROVIDER_RULE") return "Provider rule";
  if (source === "MANUAL") return "Manual";
  return source;
}

function statusLabel(status: string | null | undefined, classification: string | null | undefined): string {
  if (status === "UNMAPPED" || classification === "UNMAPPED" || !classification) {
    return "Needs classification";
  }
  if (status === "CONFIRMED") return "Confirmed";
  return status ?? "—";
}

type GroupApplyState = {
  category: string;
  rememberMapping: boolean;
};

export default function FuelBvdCanonicalClassificationPanel({ importId, canManage }: Props) {
  const [rows, setRows] = useState<FuelCanonicalTransaction[]>([]);
  const [groups, setGroups] = useState<FuelUnresolvedReasonGroup[]>([]);
  const [summary, setSummary] = useState<FuelClassificationSummary | null>(null);
  const [audit, setAudit] = useState<FuelClassificationAuditEvent[]>([]);
  const [categories, setCategories] = useState<FuelChargeCategory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAudit, setShowAudit] = useState(false);
  const [groupState, setGroupState] = useState<Record<string, GroupApplyState>>({});
  const [rowApply, setRowApply] = useState<Record<number, { category: string; remember: boolean; bulk: boolean }>>(
    {},
  );

  const groupKey = (g: FuelUnresolvedReasonGroup) =>
    `${g.provider_code}|${g.provider_section_raw}|${g.normalized_reason_key}`;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [txns, cats, sum, gr, aud] = await Promise.all([
        getFuelBvdCanonicalTransactions(importId),
        getFuelChargeCategories(),
        getFuelBvdClassificationSummary(importId),
        getFuelBvdUnresolvedClassificationGroups(importId),
        getFuelBvdClassificationAudit(importId),
      ]);
      setRows(txns);
      setCategories(cats.filter((c) => c.code !== "UNMAPPED"));
      setSummary(sum);
      setGroups(gr);
      setAudit(aud);
    } catch (e: unknown) {
      setRows([]);
      setError(e instanceof Error ? e.message : "Canonical classification unavailable");
    } finally {
      setLoading(false);
    }
  }, [importId]);

  useEffect(() => {
    void load();
  }, [load]);

  const rememberPreview = useMemo(() => {
    return (provider: string, section: string, reasonRaw: string, category: string) => (
      <div className="mt-1 rounded border border-dashed border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2 py-1 text-[10px] text-[var(--trk-text-muted)]">
        Remember for future: <span className="font-medium text-[var(--trk-text)]">{provider}</span> /{" "}
        <span className="font-medium text-[var(--trk-text)]">{section}</span>
        <br />
        &quot;{reasonRaw}&quot; → <span className="font-medium text-[var(--trk-text)]">{category}</span>
      </div>
    );
  }, []);

  const applyRow = async (txnId: number) => {
    const cfg = rowApply[txnId];
    if (!cfg?.category || cfg.category === "UNMAPPED") return;
    await setFuelTransactionClassification(txnId, {
      canonical_category: cfg.category,
      remember_mapping: cfg.remember,
      apply_matching_in_import: cfg.bulk,
    });
    await load();
  };

  const applyGroup = async (g: FuelUnresolvedReasonGroup) => {
    const cfg = groupState[groupKey(g)];
    if (!cfg?.category) return;
    await classifyFuelReasonGroup(importId, {
      provider_section_raw: g.provider_section_raw,
      provider_reason_raw: g.provider_reason_raw,
      canonical_category: cfg.category,
      remember_mapping: cfg.rememberMapping,
    });
    await load();
  };

  if (loading) {
    return <p className="text-sm text-[var(--trk-text-muted)]">Loading classification…</p>;
  }
  if (error) {
    return null;
  }
  if (!rows.length) {
    return null;
  }

  return (
    <section className="mt-6 border-t border-[var(--trk-border)] pt-4" data-testid="fuel-classification-panel">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[var(--trk-text)]">Classification</h3>
          <p className="mt-1 text-xs text-[var(--trk-text-muted)]">
            Provider source above is read-only. Category is operational metadata only — amounts, units, drivers, and
            provider reason are never edited here.
          </p>
        </div>
        {summary ? (
          <div className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-3 py-2 text-xs">
            <div className="font-medium text-[var(--trk-text)]">Summary</div>
            <div className="text-[var(--trk-text-muted)]">
              Confirmed {summary.confirmed} · Needs review {summary.needs_review}
            </div>
          </div>
        ) : null}
      </div>

      {groups.length > 0 ? (
        <div className="mt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
            Needs classification
          </h4>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[var(--trk-text-muted)]">
                  <th className="py-1 pr-2">Provider</th>
                  <th className="py-1 pr-2">Section</th>
                  <th className="py-1 pr-2">Reason</th>
                  <th className="py-1 pr-2">Count</th>
                  <th className="py-1 pr-2">Total</th>
                  <th className="py-1 pr-2">Category</th>
                  <th className="py-1 pr-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => {
                  const key = groupKey(g);
                  const st = groupState[key] ?? { category: "", rememberMapping: false };
                  return (
                    <tr key={key} className="border-t border-[var(--trk-border-subtle)] align-top">
                      <td className="py-2 pr-2">{g.provider_code}</td>
                      <td className="py-2 pr-2">{g.provider_section_raw}</td>
                      <td className="py-2 pr-2">{g.provider_reason_raw}</td>
                      <td className="py-2 pr-2">{g.transaction_count}</td>
                      <td className="py-2 pr-2">{g.total_amount}</td>
                      <td className="py-2 pr-2">
                        {canManage ? (
                          <select
                            className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-1 py-0.5"
                            value={st.category}
                            onChange={(e) =>
                              setGroupState((prev) => ({
                                ...prev,
                                [key]: { ...st, category: e.target.value },
                              }))
                            }
                          >
                            <option value="">Select…</option>
                            {categories.map((c) => (
                              <option key={c.code} value={c.code}>{c.display_name}</option>
                            ))}
                          </select>
                        ) : (
                          "UNMAPPED"
                        )}
                      </td>
                      <td className="py-2 pr-2">
                        {canManage && st.category ? (
                          <div className="space-y-1">
                            <label className="flex items-center gap-1">
                              <input
                                type="checkbox"
                                checked={st.rememberMapping}
                                onChange={(e) =>
                                  setGroupState((prev) => ({
                                    ...prev,
                                    [key]: { ...st, rememberMapping: e.target.checked },
                                  }))
                                }
                              />
                              Remember this exact wording
                            </label>
                            {st.rememberMapping
                              ? rememberPreview(
                                  g.provider_code,
                                  g.provider_section_raw,
                                  g.provider_reason_raw,
                                  st.category,
                                )
                              : null}
                            <button
                              type="button"
                              className="rounded bg-[var(--trk-accent)] px-2 py-0.5 text-white"
                              onClick={() => void applyGroup(g)}
                            >
                              Apply to {g.transaction_count} matching
                            </button>
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-xs text-[var(--trk-text-muted)]">All canonical rows are classified.</p>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          className="text-xs text-[var(--trk-accent)] hover:underline"
          onClick={() => setShowAudit((v) => !v)}
        >
          {showAudit ? "Hide" : "Show"} classification history
        </button>
        <span className="text-[10px] text-[var(--trk-text-muted)]">
          (Separate from provider source correction history.)
        </span>
      </div>
      {showAudit && audit.length > 0 ? (
        <ul className="mt-2 max-h-40 overflow-y-auto text-[10px] text-[var(--trk-text-muted)]">
          {audit.map((e) => (
            <li key={e.id} className="border-t border-[var(--trk-border-subtle)] py-1">
              #{e.fuel_transaction_id}: {e.previous_category ?? "—"} → {e.proposed_category} ({e.source ?? "—"})
              {e.actor_user_id ? ` · ${e.actor_user_id}` : ""}
              {e.created_at ? ` · ${e.created_at}` : ""}
              {e.remember_mapping ? " · remembered" : ""}
            </li>
          ))}
        </ul>
      ) : null}

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-medium text-[var(--trk-text-muted)]">
          All canonical transactions
        </summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-[var(--trk-text-muted)]">
                <th className="py-1 pr-2">Auth / ref</th>
                <th className="py-1 pr-2">Section</th>
                <th className="py-1 pr-2">Reason / product</th>
                <th className="py-1 pr-2">Total</th>
                <th className="py-1 pr-2">Category</th>
                <th className="py-1 pr-2">Status</th>
                <th className="py-1 pr-2">Source</th>
                <th className="py-1 pr-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const cfg = rowApply[r.id] ?? { category: "", remember: false, bulk: false };
                const needs = statusLabel(r.classification_status, r.classification) === "Needs classification";
                return (
                  <tr key={r.id} className="border-t border-[var(--trk-border-subtle)] align-top">
                    <td className="py-1 pr-2 font-mono">{r.provider_transaction_identity ?? "—"}</td>
                    <td className="py-1 pr-2">{r.provider_section_raw ?? "—"}</td>
                    <td className="py-1 pr-2">{r.provider_reason_raw ?? r.product_code_raw ?? "—"}</td>
                    <td className="py-1 pr-2">{r.total_amount ?? "—"}</td>
                    <td className="py-1 pr-2">{r.classification ?? "UNMAPPED"}</td>
                    <td className="py-1 pr-2">{statusLabel(r.classification_status, r.classification)}</td>
                    <td className="py-1 pr-2">{classificationSourceLabel(r.classification_source)}</td>
                    <td className="py-1 pr-2">
                      {canManage && needs && r.provider_reason_raw ? (
                        <div className="space-y-1">
                          <select
                            className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-1 py-0.5"
                            value={cfg.category}
                            onChange={(e) =>
                              setRowApply((prev) => ({
                                ...prev,
                                [r.id]: { ...cfg, category: e.target.value },
                              }))
                            }
                          >
                            <option value="">Select…</option>
                            {categories.map((c) => (
                              <option key={c.code} value={c.code}>{c.display_name}</option>
                            ))}
                          </select>
                          <label className="flex items-center gap-1">
                            <input
                              type="checkbox"
                              checked={cfg.bulk}
                              onChange={(e) =>
                                setRowApply((prev) => ({
                                  ...prev,
                                  [r.id]: { ...cfg, bulk: e.target.checked },
                                }))
                              }
                            />
                            Apply to identical reasons in this invoice
                          </label>
                          <label className="flex items-center gap-1">
                            <input
                              type="checkbox"
                              checked={cfg.remember}
                              onChange={(e) =>
                                setRowApply((prev) => ({
                                  ...prev,
                                  [r.id]: { ...cfg, remember: e.target.checked },
                                }))
                              }
                            />
                            Remember this exact wording
                          </label>
                          {cfg.remember && cfg.category
                            ? rememberPreview(
                                r.source_vendor ?? "BVD",
                                r.provider_section_raw ?? "",
                                r.provider_reason_raw ?? "",
                                cfg.category,
                              )
                            : null}
                          {cfg.category ? (
                            <button
                              type="button"
                              className="rounded bg-[var(--trk-accent)] px-2 py-0.5 text-white"
                              onClick={() => void applyRow(r.id)}
                            >
                              Apply to this transaction
                            </button>
                          ) : null}
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
