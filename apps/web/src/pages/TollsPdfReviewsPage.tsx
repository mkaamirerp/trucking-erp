import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  getTollPdfReview,
  listTollPdfReviews,
  uploadTollPdfFile,
  type TollPdfIntakeResult,
  type TollPdfReviewDetail,
  type TollPdfReviewListItem,
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
      setError(apiErrorMessage(err));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList(appliedQuery);
  }, [appliedQuery, loadList]);

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
    if (!file) {
      setUploadNote("Choose a PDF file before uploading.");
      return;
    }
    setUploadBusy(true);
    setUploadNote(null);
    try {
      const result: TollPdfIntakeResult = await uploadTollPdfFile(
        file,
        "EZPASS_WVPA_MONTHLY_STATEMENT_PDF",
      );
      const duplicate =
        result.duplicate_match_count > 0
          ? ` Same file content already stored on ${result.duplicate_match_count} earlier import${
              result.duplicate_match_count === 1 ? "" : "s"
            }. A new FILE batch was created.`
          : "";
      const recon = result.reconciliation_ok
        ? " Reconciliation matches source controls."
        : " Reconciliation did not match; kept for review, not posted.";
      setUploadNote(`E-ZPass/WVPA PDF stored for review.${duplicate}${recon}`);
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
          PDF reviews are parsed statement evidence. Canonical toll transactions are not created from this screen.
        </p>
        <div className="mt-3">
          <TollsModuleNav active="pdf" />
        </div>
      </div>

      <form onSubmit={onUpload} className="space-y-3 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4">
        <h2 className="text-sm font-semibold text-[var(--trk-text)]">Upload E-ZPass/WVPA monthly statement PDF</h2>
        <p className="text-sm text-[var(--trk-text-muted)]">
          Explicit profile EZPASS_WVPA_MONTHLY_STATEMENT_PDF. PDF is a FILE format, not a provider.
          Stores the original PDF and parsed review rows. Does not post canonical tolls.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={(ev) => {
            setFile(ev.target.files?.[0] ?? null);
            setUploadNote(null);
          }}
          className="block w-full text-sm text-[var(--trk-text-muted)] file:mr-3 file:rounded-md file:border file:border-[var(--trk-border)] file:bg-[var(--trk-surface)] file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-[var(--trk-text)]"
        />
        {uploadNote ? <p className="text-sm text-[var(--trk-text-muted)]">{uploadNote}</p> : null}
        <button
          type="submit"
          disabled={uploadBusy || !file}
          className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
        >
          {uploadBusy ? "Uploading…" : "Upload PDF"}
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
            Review-stage only. NEEDS_REVIEW means parsed and awaiting human review. It is not processed.
          </p>
        </div>
        {loading ? <p className="text-sm text-[var(--trk-text-muted)]">Loading PDF reviews…</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState
            title="No PDF reviews"
            description="Upload an E-ZPass/WVPA monthly statement PDF to store review rows. Canonical toll transactions are not created."
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

function PdfReviewRows({
  detail,
  loadingMore,
  onLoadMore,
}: {
  detail: TollPdfReviewDetail;
  loadingMore: boolean;
  onLoadMore: () => void;
}) {
  const total = detail.total_row_count || detail.parsed_trip_count;
  const hasMore = detail.rows.length < total;
  return (
    <div className="space-y-3">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--trk-text-muted)]">
        Parsed review rows
      </p>
      <p className="text-xs text-[var(--trk-text-muted)]">
        Account {detail.account_number || "—"} · pages {detail.source_page_count ?? "—"} · profile{" "}
        {detail.profile_code}. Unmapped source data — not canonical Date/Unit/Amount history.
      </p>
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
        ]}
      >
        {detail.rows.map((row) => (
          <tr key={row.source_row_order}>
            <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">{row.source_row_order}</td>
            <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">{row.source_page_number ?? "—"}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{row.agency_raw ?? "—"}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{row.post_date ?? "—"}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {[row.entry_date, row.entry_time].filter(Boolean).join(" ") || "—"}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {[row.exit_date, row.exit_time].filter(Boolean).join(" ") || "—"}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {[row.entry_location, row.entry_lane].filter(Boolean).join(" / ") || "—"}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {[row.exit_location, row.exit_lane].filter(Boolean).join(" / ") || "—"}
            </td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{row.transponder_number ?? "—"}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{row.plate_number ?? "—"}</td>
            <td className="px-4 py-2 text-sm text-[var(--trk-text)]">
              {row.trip_charge}
              {row.trip_charge_raw ? ` (${row.trip_charge_raw})` : ""}
            </td>
          </tr>
        ))}
      </Table>
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
