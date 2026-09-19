import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  confirmFuelReviewRow,
  fuelReviewDocumentUrl,
  getFuelReviewWorkspace,
  processFuelBatchReview,
  startFuelBatchReview,
  type FuelReviewCorrectionWrite,
  type FuelReviewRow,
  type FuelReviewWorkspace,
} from "../api";
import { OPS } from "../routes";

const DISPLAY_FIELDS = [
  "transaction_datetime_source",
  "unit_number_snapshot",
  "card_or_account_id",
  "driver_name_snapshot",
  "merchant_site",
  "merchant_network",
  "site_name",
  "city",
  "province_state",
  "product",
  "quantity",
  "quantity_unit",
  "unit_price",
  "unit_price_basis",
  "currency",
  "currency_raw",
  "total_amount",
  "declared_amount",
  "control_type",
  "control_scope",
  "control_label_raw",
  "gst_amount",
  "hst_amount",
  "qst_amount",
  "row_role",
] as const;

function displayValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/**
 * Provider-neutral Fuel review workspace.
 * LEFT: original source PDF. RIGHT: parsed/reviewed rows.
 * Save & Next = source review only — never posting.
 */
export default function FuelReviewWorkspacePage() {
  const { batchId: batchIdParam } = useParams();
  const batchId = Number(batchIdParam);
  const [workspace, setWorkspace] = useState<FuelReviewWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [selectedField, setSelectedField] = useState<string>("");

  const current = workspace?.current_row ?? null;
  const reviewVersion = workspace?.batch.review_version;

  const load = useCallback(async () => {
    const data = await getFuelReviewWorkspace(batchId);
    setWorkspace(data);
    return data;
  }, [batchId]);

  useEffect(() => {
    if (!Number.isFinite(batchId)) {
      setError("Invalid batch id");
      setLoading(false);
      return;
    }
    setLoading(true);
    load()
      .then(async (data) => {
        if (data.batch.status === "REVIEW_REQUIRED" || data.batch.status === "PARSED") {
          await startFuelBatchReview(batchId, data.batch.review_version);
          await load();
        }
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load workspace"))
      .finally(() => setLoading(false));
  }, [batchId, load]);

  useEffect(() => {
    if (!current) {
      setDraft({});
      setSelectedField("");
      setReason("");
      return;
    }
    const next: Record<string, string> = {};
    for (const key of current.editable_fields) {
      const v = current.fields[key];
      next[key] = v === null || v === undefined ? "" : String(v);
    }
    setDraft(next);
    setSelectedField("");
    setReason("");
  }, [current?.entity_type, current?.entity_id]);

  const fieldKeys = useMemo(() => {
    if (!current) return [] as string[];
    const preferred = DISPLAY_FIELDS.filter((k) => k in current.fields || current.editable_fields.includes(k));
    const rest = current.editable_fields.filter((k) => !preferred.includes(k as (typeof DISPLAY_FIELDS)[number]));
    return [...preferred, ...rest];
  }, [current]);

  const docUrl = Number.isFinite(batchId) ? fuelReviewDocumentUrl(batchId) : null;

  async function onSaveNext(e: FormEvent) {
    e.preventDefault();
    if (!current || workspace == null) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const corrections: FuelReviewCorrectionWrite[] = [];
      for (const field of current.editable_fields) {
        const original = current.fields[field];
        const originalStr = original === null || original === undefined ? "" : String(original);
        const nextStr = draft[field] ?? "";
        if (nextStr === originalStr) continue;
        if (!reason.trim()) {
          throw new Error("Correction reason is required when changing a value");
        }
        let reviewed_value: unknown = nextStr === "" ? null : nextStr;
        if (field === "requires_review") {
          reviewed_value = nextStr === "true";
        }
        corrections.push({ field, reviewed_value, reason: reason.trim() });
      }
      const out = await confirmFuelReviewRow(batchId, current.entity_type, current.entity_id, {
        expected_version: reviewVersion,
        corrections,
      });
      setNotice(
        out.next_row
          ? `Saved row ${current.entity_type} #${current.entity_id}. Next unresolved row loaded.`
          : `Saved row ${current.entity_type} #${current.entity_id}. All rows reviewed — Process when ready.`,
      );
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function onProcess() {
    if (!workspace) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const out = await processFuelBatchReview(batchId, workspace.batch.review_version);
      setNotice(out.message);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Process failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="p-6 text-sm text-gray-500">Loading review workspace…</div>;
  }
  if (!workspace) {
    return (
      <div className="p-6">
        <p className="text-sm text-red-700">{error || "Workspace unavailable"}</p>
        <Link to={OPS.FUEL_REVIEW} className="mt-2 inline-block text-sm text-blue-700 hover:underline">
          Back to queue
        </Link>
      </div>
    );
  }

  const batch = workspace.batch;
  const canProcess = workspace.progress.pending_rows === 0;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b bg-white px-4 py-3">
        <div>
          <div className="flex items-center gap-3">
            <Link to={OPS.FUEL_REVIEW} className="text-sm text-blue-700 hover:underline">
              ← Queue
            </Link>
            <h1 className="text-lg font-semibold text-gray-900">
              {batch.provider_code} · batch #{batch.batch_id}
            </h1>
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700">{batch.status}</span>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            Profile {batch.provider_profile_code || "—"} · layout {batch.layout_status || "—"} · parser{" "}
            {batch.parser_rule_version || "—"} · review v{batch.review_version}
          </p>
          {batch.layout_problems?.length ? (
            <p className="mt-1 text-xs font-medium text-red-700">
              Layout/profile attention: {batch.layout_problems.join(", ")}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right text-xs text-gray-600">
            <div>
              Progress {workspace.progress.confirmed_rows}/{workspace.progress.total_rows}
            </div>
            <div>{workspace.progress.pending_rows} pending</div>
          </div>
          <button
            type="button"
            disabled={!canProcess || saving || batch.status === "READY_FOR_RECONCILIATION"}
            onClick={() => void onProcess()}
            className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
            title={workspace.process_boundary.message}
          >
            Process
          </button>
        </div>
      </header>

      {(error || notice) && (
        <div className="border-b px-4 py-2 text-sm">
          {error && <div className="text-red-700">{error}</div>}
          {notice && <div className="text-emerald-800">{notice}</div>}
          <div className="text-xs text-gray-500">{workspace.process_boundary.message}</div>
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
        <section className="min-h-0 border-r bg-gray-100">
          <div className="border-b bg-white px-3 py-2 text-xs font-medium uppercase tracking-wide text-gray-500">
            Original source (immutable)
          </div>
          {docUrl && batch.source_type === "PDF" ? (
            <iframe title="Fuel source PDF" src={docUrl} className="h-[calc(100%-2rem)] w-full bg-white" />
          ) : (
            <div className="p-4 text-sm text-gray-600">
              <p>Document reference: {batch.source_storage_ref || "—"}</p>
              <p className="mt-2 text-xs text-gray-500">{workspace.document.note}</p>
            </div>
          )}
        </section>

        <section className="flex min-h-0 flex-col overflow-hidden bg-white">
          <div className="border-b px-3 py-2 text-xs font-medium uppercase tracking-wide text-gray-500">
            Extracted transactions & controls
          </div>
          <div className="max-h-40 overflow-y-auto border-b">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="px-2 py-1">#</th>
                  <th className="px-2 py-1">Type</th>
                  <th className="px-2 py-1">Role</th>
                  <th className="px-2 py-1">Review</th>
                  <th className="px-2 py-1">Warnings</th>
                </tr>
              </thead>
              <tbody>
                {workspace.rows.map((row) => (
                  <tr
                    key={`${row.entity_type}-${row.entity_id}`}
                    className={
                      current &&
                      current.entity_type === row.entity_type &&
                      current.entity_id === row.entity_id
                        ? "bg-blue-50"
                        : ""
                    }
                  >
                    <td className="px-2 py-1">{row.source_row_order ?? "—"}</td>
                    <td className="px-2 py-1">{row.entity_type}</td>
                    <td className="px-2 py-1">{row.effective_row_role}</td>
                    <td className="px-2 py-1">{row.review_status}</td>
                    <td className="px-2 py-1 text-amber-800">{row.warnings.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {!current ? (
              <p className="text-sm text-gray-600">
                All rows confirmed. Use Process to mark the batch READY_FOR_RECONCILIATION (Segment 9
                will reconcile later).
              </p>
            ) : (
              <CurrentRowEditor
                row={current}
                fieldKeys={fieldKeys}
                draft={draft}
                setDraft={setDraft}
                reason={reason}
                setReason={setReason}
                selectedField={selectedField}
                setSelectedField={setSelectedField}
                saving={saving}
                onSaveNext={onSaveNext}
                corrections={workspace.corrections.filter(
                  (c) =>
                    c.entity_type === current.entity_type && Number(c.entity_id) === current.entity_id,
                )}
              />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function CurrentRowEditor(props: {
  row: FuelReviewRow;
  fieldKeys: string[];
  draft: Record<string, string>;
  setDraft: (v: Record<string, string>) => void;
  reason: string;
  setReason: (v: string) => void;
  selectedField: string;
  setSelectedField: (v: string) => void;
  saving: boolean;
  onSaveNext: (e: FormEvent) => void;
  corrections: Array<Record<string, unknown>>;
}) {
  const { row, fieldKeys, draft, setDraft, reason, setReason, saving, onSaveNext, corrections } = props;
  return (
    <form onSubmit={onSaveNext} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold text-gray-900">
          Current: {row.entity_type} #{row.entity_id}
        </h2>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">
          parsed role {row.parsed_row_role}
          {row.reviewed_row_role ? ` → reviewed ${row.reviewed_row_role}` : ""}
        </span>
      </div>
      {row.warnings.length > 0 && (
        <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {row.warnings.join(" · ")}
        </div>
      )}

      <div className="space-y-2">
        {fieldKeys.map((field) => {
          const parsed = row.fields[field];
          const editable = row.editable_fields.includes(field);
          return (
            <div key={field} className="grid grid-cols-1 gap-1 rounded border border-gray-100 p-2 md:grid-cols-3">
              <div className="text-xs font-medium text-gray-700">{field}</div>
              <div className="text-xs text-gray-500">
                <div className="uppercase tracking-wide">Parsed / current</div>
                <div className="font-mono text-gray-800">{displayValue(parsed)}</div>
              </div>
              <div>
                {editable ? (
                  <input
                    className="w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
                    value={draft[field] ?? ""}
                    onChange={(e) => setDraft({ ...draft, [field]: e.target.value })}
                    placeholder="Reviewed value (blank = null)"
                  />
                ) : (
                  <div className="text-xs text-gray-400">read-only</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-700" htmlFor="fuel-review-reason">
          Correction reason (required when any value changes)
        </label>
        <textarea
          id="fuel-review-reason"
          className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>

      <div className="rounded border border-dashed border-gray-200 p-2">
        <div className="text-xs font-medium text-gray-500">provider_raw (immutable)</div>
        <pre className="mt-1 max-h-32 overflow-auto text-[11px] text-gray-600">
          {JSON.stringify(row.provider_raw, null, 2)}
        </pre>
      </div>

      {corrections.length > 0 && (
        <div className="rounded border border-gray-200 p-2 text-xs">
          <div className="font-medium text-gray-700">Correction history</div>
          <ul className="mt-1 space-y-1 text-gray-600">
            {corrections.map((c) => (
              <li key={String(c.id)}>
                {String(c.field_name)}: {displayValue(c.parsed_value)} → {displayValue(c.reviewed_value)} (
                {String(c.reason)})
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 border-t pt-3">
        <p className="text-xs text-gray-500">
          Save &amp; Next confirms source review for this row only. It does not post or reconcile.
        </p>
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300"
        >
          {saving ? "Saving…" : "Save & Next"}
        </button>
      </div>
    </form>
  );
}
