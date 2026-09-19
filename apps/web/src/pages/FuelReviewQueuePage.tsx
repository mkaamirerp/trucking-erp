import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listFuelReviewQueue, type FuelReviewQueueItem } from "../api";
import { OPS } from "../routes";

/**
 * Generic Fuel source review queue (provider-neutral).
 * Review is source extraction review only — not posting / reconciliation.
 */
export default function FuelReviewQueuePage() {
  const [rows, setRows] = useState<FuelReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const data = await listFuelReviewQueue();
    setRows(data);
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load review queue"))
      .finally(() => setLoading(false));
  }, [refresh]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Fuel source review</h1>
          <p className="mt-1 text-sm text-gray-600">
            Verify extracted transactions and controls against the original provider source.
            Completing review does not post, reconcile, or settle.
          </p>
        </div>
        <Link to={OPS.FUEL_PROVIDERS} className="text-sm text-blue-700 hover:underline">
          Providers
        </Link>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
      )}
      {loading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-gray-500">No batches currently in the review queue.</p>
      ) : (
        <div className="overflow-x-auto rounded border border-gray-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2">Provider</th>
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Invoice / statement</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Rows</th>
                <th className="px-3 py-2">Problems</th>
                <th className="px-3 py-2">Profile / layout</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.batch_id} className="border-b last:border-0">
                  <td className="px-3 py-2 font-medium text-gray-900">{row.provider_code}</td>
                  <td className="px-3 py-2 text-gray-700">
                    <div>{row.source_type}</div>
                    <div className="text-xs text-gray-500">{row.remote_filename || row.source_storage_ref || "—"}</div>
                  </td>
                  <td className="px-3 py-2 text-gray-700">
                    <div>{row.invoice_number || "—"}</div>
                    <div className="text-xs text-gray-500">
                      {[row.statement_start, row.statement_end].filter(Boolean).join(" → ") ||
                        row.invoice_date ||
                        "—"}
                    </div>
                    {row.currencies?.length ? (
                      <div className="text-xs text-gray-500">{row.currencies.join(", ")}</div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900">
                      {row.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-700">
                    {row.transaction_count} txn / {row.control_count} ctrl
                    <div className="text-xs text-gray-500">{row.pending_review_count} pending</div>
                  </td>
                  <td className="px-3 py-2 text-gray-700">
                    {row.problem_count}
                    {row.layout_problems?.length ? (
                      <div className="max-w-[14rem] truncate text-xs text-red-700" title={row.layout_problems.join(", ")}>
                        {row.layout_problems.join(", ")}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-600">
                    <div>{row.provider_profile_code || "—"}</div>
                    <div>{row.layout_status || "—"}</div>
                    <div className="text-gray-400">{row.parser_rule_version || ""}</div>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Link
                      to={OPS.FUEL_REVIEW_BATCH(row.batch_id)}
                      className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
