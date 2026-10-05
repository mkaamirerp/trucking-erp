import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  getTollFileBatch,
  listTollFileBatches,
  uploadTollCsvFile,
  type TollCsvIntakeResult,
  type TollFileBatchDetail,
  type TollFileBatchListItem,
} from "../api";
import EmptyState from "../components/EmptyState";
import { Table } from "../components/Table";

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

function shortenHash(hash: string | null): string {
  if (!hash) return "—";
  if (hash.length <= 12) return hash;
  return `${hash.slice(0, 8)}…${hash.slice(-4)}`;
}

function formatImportedAt(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function parsedStatusNote(status: string): string {
  if (status === "PARSED") {
    return "file received + generic CSV parsed";
  }
  return status;
}

export default function TollsHistoryPage() {
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [items, setItems] = useState<TollFileBatchListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<TollFileBatchDetail | null>(null);
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
      const rows = await listTollFileBatches(search);
      setItems(rows);
      if (preferBatchId != null) {
        setExpandedId(preferBatchId);
      }
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
    getTollFileBatch(expandedId, { rowOffset: 0, rowLimit: 100 })
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

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setAppliedQuery(query.trim());
  }

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setUploadNote("Choose a CSV file before uploading.");
      return;
    }
    setUploadBusy(true);
    setUploadNote(null);
    try {
      const result: TollCsvIntakeResult = await uploadTollCsvFile(file);
      const duplicate =
        result.duplicate_match_count > 0
          ? ` Same file content already stored on ${result.duplicate_match_count} earlier import${
              result.duplicate_match_count === 1 ? "" : "s"
            } (${result.duplicate_batch_ids.join(", ")}). A new FILE batch was created; both copies are kept.`
          : "";
      setUploadNote(`CSV uploaded and stored for mapping.${duplicate}`);
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
          CSV file imports and unmapped source rows. This is not canonical toll transaction history.
          Date/Time, Unit, Toll Agency, Amount, Type, Read By, and Identifier are not available until
          a provider mapping exists.
        </p>
      </div>

      <form onSubmit={onUpload} className="space-y-3 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4">
        <h2 className="text-sm font-semibold text-[var(--trk-text)]">Upload CSV</h2>
        <p className="text-sm text-[var(--trk-text-muted)]">
          Stores the original file as a FILE batch. Does not create canonical toll transactions.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv,text/plain"
          onChange={(ev) => {
            setFile(ev.target.files?.[0] ?? null);
            setUploadNote(null);
          }}
          className="block w-full text-sm text-[var(--trk-text-muted)] file:mr-3 file:rounded-md file:border file:border-[var(--trk-border)] file:bg-[var(--trk-surface)] file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-[var(--trk-text)] hover:file:bg-[var(--trk-surface-2)]"
        />
        {uploadNote ? <p className="text-sm text-[var(--trk-text-muted)]">{uploadNote}</p> : null}
        <button
          type="submit"
          disabled={uploadBusy || !file}
          className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
        >
          {uploadBusy ? "Uploading…" : "Upload CSV"}
        </button>
      </form>

      <form onSubmit={onSearch} className="flex flex-wrap items-end gap-3">
        <label className="min-w-[16rem] flex-1 text-sm font-medium text-[var(--trk-text)]">
          Search filename or source hash
          <input
            value={query}
            onChange={(ev) => setQuery(ev.target.value)}
            className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)]"
            placeholder="tolls.csv or sha256…"
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
          <h2 className="text-sm font-semibold text-[var(--trk-text)]">File Imports</h2>
          <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
            CSV import history. Status PARSED means the file was received and the generic CSV was parsed.
            It does not mean canonical tolls were processed.
          </p>
        </div>
        {loading ? <p className="text-sm text-[var(--trk-text-muted)]">Loading file imports…</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState
            title="No CSV imports"
            description="Upload a CSV to store a FILE batch and unmapped source rows. Canonical toll transactions are not created from this upload."
          />
        ) : null}
        {!loading && items.length > 0 ? (
          <Table headers={["Batch", "Filename", "Format", "Source rows", "Status", "Imported", "Hash"]}>
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
                    {item.source_type}
                    {item.file_format ? ` / ${item.file_format}` : ""}
                  </td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{item.row_count}</td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">
                    <span>{item.status}</span>
                    {item.status === "PARSED" ? (
                      <span className="mt-0.5 block text-xs">
                        {parsedStatusNote(item.status)} — not canonical processed
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">
                    {formatImportedAt(item.imported_at)}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-[var(--trk-text-muted)]" title={item.source_hash ?? ""}>
                    {shortenHash(item.source_hash)}
                  </td>
                </tr>,
              ];
              if (open) {
                rows.push(
                  <tr key={`${item.batch_id}-detail`}>
                    <td colSpan={7} className="bg-[var(--trk-surface-2)] px-4 py-3">
                      {detailLoading ? (
                        <p className="text-sm text-[var(--trk-text-muted)]">Loading source rows…</p>
                      ) : null}
                      {detailError ? <p className="text-sm text-red-600">{detailError}</p> : null}
                      {detail && detail.batch_id === item.batch_id ? (
                        <RawSourceRowsTable
                          detail={detail}
                          loadingMore={rowLoadingMore}
                          onLoadMore={async () => {
                            if (rowLoadingMore) return;
                            setRowLoadingMore(true);
                            try {
                              const next = await getTollFileBatch(item.batch_id, {
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

function RawSourceRowsTable({
  detail,
  loadingMore,
  onLoadMore,
}: {
  detail: TollFileBatchDetail;
  loadingMore: boolean;
  onLoadMore: () => void;
}) {
  if (!detail.rows.length) {
    return <p className="text-sm text-[var(--trk-text-muted)]">No source rows in this FILE batch.</p>;
  }
  const headers = (detail.csv_column_keys && detail.csv_column_keys.length
    ? detail.csv_column_keys
    : detail.headers) || [];
  const total = detail.total_row_count || detail.row_count;
  const hasMore = detail.rows.length < total;
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--trk-text-muted)]">
        Raw source rows
      </p>
      <p className="text-xs text-[var(--trk-text-muted)]">
        Unmapped source data — original CSV cells, not normalized toll fields.
      </p>
      <p className="text-xs text-[var(--trk-text-muted)]">
        Showing {detail.rows.length} of {total}
      </p>
      <Table headers={["#", "Line", ...headers]}>
        {detail.rows.map((row) => (
          <tr key={row.source_row_order}>
            <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">{row.source_row_order}</td>
            <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">
              {row.source_line_number ?? "—"}
            </td>
            {headers.map((header) => (
              <td key={header} className="px-4 py-2 text-sm text-[var(--trk-text)]">
                {row.cells[header] ?? ""}
              </td>
            ))}
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
