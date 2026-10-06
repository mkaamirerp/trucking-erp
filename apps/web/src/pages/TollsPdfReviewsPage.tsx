import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  getTollPdfReview,
  listTollPdfReviews,
  listTollProviders,
  patchTollPdfReviewRow,
  processTollPdfReview,
  uploadTollFile,
  type TollPdfIntakeResult,
  type TollPdfReviewDetail,
  type TollPdfReviewListItem,
  type TollPdfReviewRow,
  type TollProviderCatalog,
  type TollUploadProvider,
} from "../api";
import EmptyState from "../components/EmptyState";
import { Table } from "../components/Table";
import TollsModuleNav from "./TollsModuleNav";

function apiErrorMessage(err: unknown): string {
  if (!(err instanceof Error)) return String(err);
  try {
    const parsed = JSON.parse(err.message) as { detail?: { message?: string } | string };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (parsed.detail && typeof parsed.detail === "object" && parsed.detail.message) {
      return parsed.detail.message;
    }
  } catch {
    /* raw text */
  }
  return err.message;
}

function isQuietTollListFailure(message: string): boolean {
  const text = message.trim().toLowerCase();
  return text === "internal server error" || text.includes('"detail":"internal server error"');
}

function money(value: string | null | undefined): string {
  return value ?? "—";
}

export default function TollsPdfReviewsPage() {
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [items, setItems] = useState<TollPdfReviewListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<TollPdfReviewDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [providers, setProviders] = useState<TollProviderCatalog[]>([]);
  const [provider, setProvider] = useState<TollUploadProvider | "">("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [rowLoadingMore, setRowLoadingMore] = useState(false);

  const loadList = useCallback(async (search: string, preferBatchId?: number) => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listTollPdfReviews(search);
      setItems(rows);
      if (preferBatchId != null) setExpandedId(preferBatchId);
    } catch (err) {
      const message = apiErrorMessage(err);
      setItems([]);
      setError(isQuietTollListFailure(message) ? null : message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList(appliedQuery);
  }, [appliedQuery, loadList]);

  useEffect(() => {
    let cancelled = false;
    listTollProviders()
      .then((rows) => {
        if (!cancelled) setProviders(rows.filter((row) => row.upload_choice));
      })
      .catch((err) => {
        if (!cancelled) setUploadNote(apiErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (expandedId == null) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    getTollPdfReview(expandedId, { rowOffset: 0, rowLimit: 100 })
      .then((row) => {
        if (!cancelled) setDetail(row);
      })
      .catch((err) => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(apiErrorMessage(err));
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [expandedId]);

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!provider) {
      setUploadNote("Choose a provider before uploading.");
      return;
    }
    if (!file) {
      setUploadNote("Choose a file before uploading.");
      return;
    }
    setUploadBusy(true);
    setUploadNote(null);
    try {
      const result: TollPdfIntakeResult = await uploadTollFile(file, provider);
      const duplicate =
        result.duplicate_match_count > 0
          ? ` Same file content already stored on ${result.duplicate_match_count} earlier import${
              result.duplicate_match_count === 1 ? "" : "s"
            }. A new FILE batch was created.`
          : "";
      const recon = result.reconciliation_ok
        ? " Reconciliation matches source controls."
        : " Reconciliation did not match; kept for review, not posted.";
      setUploadNote(`E-ZPass file stored for review.${duplicate}${recon}`);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await loadList(appliedQuery, result.batch_id);
    } catch (err) {
      setUploadNote(apiErrorMessage(err));
    } finally {
      setUploadBusy(false);
    }
  }

  return (
    <div className="trk-page trk-page--constrained space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-[var(--trk-text)]">Tolls</h1>
        <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
          Upload one file. The system detects PDF, image, or CSV, then looks for Toll evidence.
        </p>
        <div className="mt-3">
          <TollsModuleNav active="upload" />
        </div>
      </div>

      <form onSubmit={onUpload} className="space-y-3 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4">
        <h2 className="text-sm font-semibold text-[var(--trk-text)]">Upload file</h2>
        <p className="text-sm text-[var(--trk-text-muted)]">
          Choose the provider, then upload one file. E-ZPass digital PDFs are processed now.
          CSV will be wired later. Other listed providers are not wired yet.
        </p>
        <label className="block text-sm font-medium text-[var(--trk-text)]">
          Provider
          <select
            value={provider}
            onChange={(ev) => setProvider(ev.target.value as TollUploadProvider | "")}
            className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm"
          >
            <option value="">Select provider</option>
            {providers.map((row) => (
              <option key={row.provider_code} value={row.provider_code}>
                {row.home_state ? `${row.provider_name} (${row.home_state})` : row.provider_name}
              </option>
            ))}
          </select>
        </label>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.csv,.jpg,.jpeg,.png,application/pdf,text/csv,image/jpeg,image/png"
          onChange={(ev) => {
            setFile(ev.target.files?.[0] ?? null);
            setUploadNote(null);
          }}
          className="block w-full text-sm text-[var(--trk-text-muted)] file:mr-3 file:rounded-md file:border file:border-[var(--trk-border)] file:bg-[var(--trk-surface)] file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-[var(--trk-text)]"
        />
        {uploadNote ? <p className="text-sm text-[var(--trk-text-muted)]">{uploadNote}</p> : null}
        <button
          type="submit"
          disabled={uploadBusy || !file || !provider}
          className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
        >
          {uploadBusy ? "Uploading…" : "Upload"}
        </button>
      </form>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          setAppliedQuery(query.trim());
        }}
        className="flex flex-wrap items-end gap-3"
      >
        <label className="min-w-[16rem] flex-1 text-sm font-medium text-[var(--trk-text)]">
          Search filename, hash, or account
          <input
            value={query}
            onChange={(ev) => setQuery(ev.target.value)}
            className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)]"
            placeholder="statement.pdf or account…"
          />
        </label>
        <button
          type="submit"
          className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-4 py-2 text-sm font-medium text-[var(--trk-text)]"
        >
          Search
        </button>
      </form>

      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-semibold text-[var(--trk-text)]">PDF Reviews</h2>
          <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
            NEEDS_REVIEW is parsed evidence awaiting correction and Process. PROCESSED means canonical rows exist.
          </p>
        </div>
        {loading ? <p className="text-sm text-[var(--trk-text-muted)]">Loading PDF reviews…</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState
            title="No PDF reviews"
            description="Upload an E-ZPass/WVPA monthly statement PDF to store review rows, then Process after reconciliation."
          />
        ) : null}
        {!loading && items.length > 0 ? (
          <Table
            headers={[
              "Batch",
              "Filename",
              "Period",
              "Source trips",
              "Parsed trips",
              "Source total",
              "Parsed total",
              "Reconciliation",
              "Review",
            ]}
          >
            {items.flatMap((item) => {
              const open = expandedId === item.batch_id;
              const rows = [
                <tr key={item.batch_id}>
                  <td className="px-4 py-2 text-sm font-medium text-[var(--trk-text)]">
                    <button
                      type="button"
                      className="text-left text-[var(--trk-accent)] underline-offset-2 hover:underline"
                      onClick={() => setExpandedId(open ? null : item.batch_id)}
                    >
                      #{item.batch_id}
                    </button>
                  </td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{item.filename || "—"}</td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">
                    {item.period_start || "—"} to {item.period_end || "—"}
                  </td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{item.source_total_trip_count ?? "—"}</td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{item.parsed_trip_count}</td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{money(item.source_total_trip_charge)}</td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{money(item.parsed_total_trip_charge)}</td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">
                    {item.reconciliation_ok ? "OK" : "Failed"}
                  </td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">{item.review_status}</td>
                </tr>,
              ];
              if (open) {
                rows.push(
                  <tr key={`${item.batch_id}-detail`}>
                    <td colSpan={9} className="bg-[var(--trk-surface-2)] px-4 py-3">
                      {detailLoading ? (
                        <p className="text-sm text-[var(--trk-text-muted)]">Loading review rows…</p>
                      ) : null}
                      {detailError ? <p className="text-sm text-red-600">{detailError}</p> : null}
                      {detail && detail.batch_id === item.batch_id ? (
                        <PdfReviewRows
                          detail={detail}
                          loadingMore={rowLoadingMore}
                          onRefresh={async () => {
                            const next = await getTollPdfReview(item.batch_id, {
                              rowOffset: 0,
                              rowLimit: Math.max(detail.rows.length, 100),
                            });
                            setDetail(next);
                            await loadList(appliedQuery, item.batch_id);
                          }}
                          onLoadMore={async () => {
                            if (rowLoadingMore) return;
                            setRowLoadingMore(true);
                            try {
                              const next = await getTollPdfReview(item.batch_id, {
                                rowOffset: detail.rows.length,
                                rowLimit: 100,
                              });
                              setDetail((prev) =>
                                prev && prev.batch_id === next.batch_id
                                  ? { ...next, rows: [...prev.rows, ...next.rows] }
                                  : next,
                              );
                            } catch (err) {
                              setDetailError(apiErrorMessage(err));
                            } finally {
                              setRowLoadingMore(false);
                            }
                          }}
                        />
                      ) : null}
                    </td>
                  </tr>,
                );
              }
              return rows;
            })}
          </Table>
        ) : null}
      </section>
    </div>
  );
}

const EDITABLE_FIELDS: { key: keyof TollPdfReviewRow; label: string }[] = [
  { key: "post_date", label: "Post date" },
  { key: "entry_date", label: "Entry date" },
  { key: "entry_time", label: "Entry time" },
  { key: "exit_date", label: "Exit date" },
  { key: "exit_time", label: "Exit time" },
  { key: "agency_raw", label: "Agency" },
  { key: "entry_location", label: "Entry location" },
  { key: "entry_lane", label: "Entry lane" },
  { key: "exit_location", label: "Exit location" },
  { key: "exit_lane", label: "Exit lane" },
  { key: "transponder_number", label: "Transponder" },
  { key: "plate_number", label: "Plate" },
  { key: "trip_charge", label: "Trip charge" },
];

function fieldValue(row: TollPdfReviewRow, key: string): string {
  const effective = row.effective?.[key];
  if (typeof effective === "string" && effective) return effective;
  const raw = row[key as keyof TollPdfReviewRow];
  return typeof raw === "string" ? raw : "";
}

function displayField(row: TollPdfReviewRow, key: string, rawFallback: string | null | undefined): string {
  const changed = (row.changed_fields || []).includes(key);
  const effective = fieldValue(row, key) || rawFallback || "—";
  if (!changed) return effective;
  const raw = rawFallback || "—";
  return `${effective} (raw ${raw})`;
}

function PdfReviewRows({
  detail,
  loadingMore,
  onLoadMore,
  onRefresh,
}: {
  detail: TollPdfReviewDetail;
  loadingMore: boolean;
  onLoadMore: () => void;
  onRefresh: () => Promise<void>;
}) {
  const total = detail.total_row_count || detail.parsed_trip_count;
  const hasMore = detail.rows.length < total;
  const processed = detail.review_status === "PROCESSED" || detail.status === "PROCESSED";
  const reconOk = detail.effective_reconciliation_ok ?? detail.reconciliation_ok;
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function onSaveCorrection() {
    if (editingId == null) return;
    setBusy(true);
    setNote(null);
    try {
      const payload: Record<string, string> = {};
      for (const field of EDITABLE_FIELDS) {
        const value = draft[field.key];
        if (value != null && value !== "") payload[field.key] = value;
      }
      await patchTollPdfReviewRow(detail.batch_id, editingId, payload);
      await onRefresh();
      setNote("Correction stored separately. Raw parser values were not changed.");
    } catch (err) {
      setNote(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onProcess() {
    setBusy(true);
    setNote(null);
    try {
      const result = await processTollPdfReview(detail.batch_id);
      await onRefresh();
      setNote(
        `Processed ${result.processed_transaction_count} TollTransaction rows totaling ${result.processed_total}.`,
      );
    } catch (err) {
      setNote(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--trk-text-muted)]">
        Parsed review rows
      </p>
      <p className="text-xs text-[var(--trk-text-muted)]">
        Account {detail.account_number || "—"} · pages {detail.source_page_count ?? "—"} · profile{" "}
        {detail.profile_code}. Unmapped source data — not canonical Date/Unit/Amount history.
      </p>
      <p className="text-sm text-[var(--trk-text)]">
        Effective {detail.effective_trip_count ?? detail.parsed_trip_count} / {detail.source_total_trip_count ?? "—"}{" "}
        trips · {detail.effective_total_trip_charge ?? detail.parsed_total_trip_charge} /{" "}
        {detail.source_total_trip_charge ?? "—"} · {reconOk ? "reconciliation OK" : "reconciliation failed"}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || processed || !reconOk}
          onClick={() => void onProcess()}
          className="rounded-md bg-[var(--trk-btn-primary)] px-3 py-1.5 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
        >
          {processed ? "Processed" : "Process"}
        </button>
      </div>
      {note ? <p className="text-sm text-[var(--trk-text-muted)]">{note}</p> : null}
      {processed ? (
        <p className="text-xs text-[var(--trk-text-muted)]">Processed PDF review is read-only.</p>
      ) : null}
      <p className="text-xs text-[var(--trk-text-muted)]">
        Showing {detail.rows.length} of {total}
      </p>
      <Table
        headers={[
          "#",
          "Page",
          "Agency",
          "Post date",
          "Entry",
          "Exit",
          "Entry loc/lane",
          "Exit loc/lane",
          "Transponder",
          "Plate",
          "Trip charge",
          "Edit",
        ]}
      >
        {detail.rows.map((row) => (
          <tr key={row.source_row_order}>
            <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">{row.source_row_order}</td>
            <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">{row.source_page_number ?? "—"}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{displayField(row, "agency_raw", row.agency_raw)}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{displayField(row, "post_date", row.post_date)}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {displayField(row, "entry_date", row.entry_date)} {displayField(row, "entry_time", row.entry_time)}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {displayField(row, "exit_date", row.exit_date)} {displayField(row, "exit_time", row.exit_time)}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {displayField(row, "entry_location", row.entry_location)} / {displayField(row, "entry_lane", row.entry_lane)}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {displayField(row, "exit_location", row.exit_location)} / {displayField(row, "exit_lane", row.exit_lane)}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {displayField(row, "transponder_number", row.transponder_number)}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{displayField(row, "plate_number", row.plate_number)}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {displayField(row, "trip_charge", row.trip_charge)}
              {row.trip_charge_raw ? ` (${row.trip_charge_raw})` : ""}
            </td>
            <td className="px-4 py-2 text-sm">
              <button
                type="button"
                disabled={processed || row.row_id == null}
                onClick={() => {
                  setEditingId(row.row_id ?? null);
                  const next: Record<string, string> = {};
                  for (const field of EDITABLE_FIELDS) {
                    next[field.key] = fieldValue(row, field.key);
                  }
                  setDraft(next);
                }}
                className="text-[var(--trk-accent)] underline-offset-2 hover:underline disabled:opacity-50"
              >
                Correct
              </button>
            </td>
          </tr>
        ))}
      </Table>
      {editingId != null && !processed ? (
        <form
          className="grid gap-2 rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] p-3 sm:grid-cols-3"
          onSubmit={(event) => {
            event.preventDefault();
            void onSaveCorrection();
          }}
        >
          <p className="sm:col-span-3 text-xs font-medium text-[var(--trk-text)]">
            Correct row #{editingId}. Raw parser evidence stays unchanged.
          </p>
          {EDITABLE_FIELDS.map((field) => (
            <label key={field.key} className="text-xs font-medium text-[var(--trk-text)]">
              {field.label}
              <input
                value={draft[field.key] ?? ""}
                onChange={(ev) => setDraft({ ...draft, [field.key]: ev.target.value })}
                className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1 text-sm"
              />
            </label>
          ))}
          <div className="sm:col-span-3 flex gap-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Save correction
            </button>
            <button
              type="button"
              onClick={() => setEditingId(null)}
              className="rounded-md border border-[var(--trk-border)] px-3 py-1.5 text-sm"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : null}
      {hasMore ? (
        <button
          type="button"
          disabled={loadingMore}
          onClick={onLoadMore}
          className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-sm text-[var(--trk-text)] disabled:opacity-50"
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      ) : null}
    </div>
  );
}
