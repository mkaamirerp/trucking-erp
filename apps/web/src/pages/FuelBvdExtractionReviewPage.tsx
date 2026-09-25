import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  fuelBvdDocumentUrl,
  getFuelBvdImportRows,
  getFuelBvdImportSummary,
  processFuelBvdImport,
  saveFuelBvdReview,
  type FuelBvdReviewSummary,
  type FuelBvdRow,
} from "../api";
import { OPS } from "../routes";
import BvdPdfViewer from "./fuelBvdReview/BvdPdfViewer";
import { loadBvdPdfDocument } from "./fuelBvdReview/loadBvdPdfDocument";
import {
  anchorFieldForRowType,
  mapPdfJsTextItems,
  resolveHighlightOnPage,
  type PdfHighlightRect,
} from "./fuelBvdReview/bvdPdfHighlight";
import { defaultTabForRowType, rowsForTab } from "./fuelBvdReview/bvdReviewTabs";
import {
  draftKey,
  extractedValue,
  type DraftMap,
  type FieldSelection,
  isFieldCorrected,
  persistedReviewed,
  reviewedValue,
} from "./fuelBvdReview/bvdReviewValues";
import {
  BVD_FIELD_LABELS,
  BVD_GRAND_TOTAL_FIELDS,
  BVD_HEADER_FIELDS,
  BVD_REVIEW_TABS,
  BVD_SUBTOTAL_FIELDS,
  BVD_TRANSACTION_COLUMNS,
  type BvdReviewTabId,
  reviewStatusLabel,
} from "./fuelBvdReviewLabels";

function ProcessConfirmModal({
  summary,
  busy,
  onCancel,
  onConfirm,
}: {
  summary: FuelBvdReviewSummary;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const amountLine =
    summary.final_amount && summary.currency
      ? `${summary.final_amount} ${summary.currency}`
      : summary.final_amount ?? "—";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] p-5 shadow-xl">
        <h2 className="text-base font-semibold text-[var(--trk-text)]">Confirm process</h2>
        <p className="mt-2 text-sm text-[var(--trk-text-muted)]">
          Source review only — no settlement, posting, or truck matching.
        </p>
        <dl className="mt-4 space-y-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--trk-text-muted)]">BVD Invoice</dt>
            <dd className="font-medium text-[var(--trk-text)]">{summary.invoice_number}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--trk-text-muted)]">Transactions</dt>
            <dd>{summary.transaction_count}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--trk-text-muted)]">Source records</dt>
            <dd>{summary.row_count}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--trk-text-muted)]">Corrections</dt>
            <dd>{summary.correction_count}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--trk-text-muted)]">Final amount</dt>
            <dd>{amountLine}</dd>
          </div>
        </dl>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-md border border-[var(--trk-border)] px-3 py-1.5 text-sm">
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-md bg-[var(--trk-btn-primary)] px-3 py-1.5 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
          >
            {busy ? "Processing…" : "Confirm process"}
          </button>
        </div>
      </div>
    </div>
  );
}

function FieldStatusBadge({ corrected }: { corrected: boolean }) {
  if (corrected) {
    return (
      <span className="rounded bg-[var(--trk-warning)]/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-[var(--trk-warning)]">
        Corrected
      </span>
    );
  }
  return (
    <span className="rounded bg-[var(--trk-success)]/15 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--trk-success)]">
      Match ✓
    </span>
  );
}

export default function FuelBvdExtractionReviewPage() {
  const { importId } = useParams();
  const [rows, setRows] = useState<FuelBvdRow[]>([]);
  const [drafts, setDrafts] = useState<DraftMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [confirmSummary, setConfirmSummary] = useState<FuelBvdReviewSummary | null>(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfZoom, setPdfZoom] = useState(100);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<BvdReviewTabId>("HEADER");
  const [selection, setSelection] = useState<FieldSelection | null>(null);
  const [highlight, setHighlight] = useState<PdfHighlightRect | null>(null);

  const load = useCallback(async () => {
    if (!importId) return;
    setRows(await getFuelBvdImportRows(importId));
    setDrafts({});
  }, [importId]);

  useEffect(() => {
    if (!importId) {
      setError("Missing import id");
      setLoading(false);
      return;
    }
    setLoading(true);
    load()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load BVD review"))
      .finally(() => setLoading(false));
  }, [importId, load]);

  useEffect(() => {
    if (!importId) return;
    setPdfLoading(true);
    setPdfError(null);
    loadBvdPdfDocument(fuelBvdDocumentUrl(importId))
      .then((doc) => setPdfDoc(doc))
      .catch((e: unknown) => setPdfError(e instanceof Error ? e.message : "PDF load failed"))
      .finally(() => setPdfLoading(false));
  }, [importId]);

  const pageCount = useMemo(
    () => Math.max(1, rows.reduce((m, r) => Math.max(m, r.source_page ?? 1), 1)),
    [rows],
  );

  const header = useMemo(() => rows.find((r) => r.row_type === "HEADER"), [rows]);
  const reviewStatus = header?.review_status ?? "PENDING";
  const readOnly = reviewStatus === "SOURCE_REVIEWED";
  const tabRows = useMemo(() => rowsForTab(rows, activeTab), [rows, activeTab]);

  const buildCorrectionsPayload = useCallback(() => {
    const corrections: { fuel_bvd_id: number; field_name: string; reviewed_value: string }[] = [];
    for (const row of rows) {
      const fields = new Set<string>();
      Object.keys(BVD_FIELD_LABELS).forEach((f) => {
        if (extractedValue(row, f) || persistedReviewed(row, f) || drafts[draftKey(row.id, f)]) fields.add(f);
      });
      for (const field of fields) {
        const ext = extractedValue(row, field);
        const rev = reviewedValue(row, field, drafts);
        if (rev !== ext) corrections.push({ fuel_bvd_id: row.id, field_name: field, reviewed_value: rev });
      }
    }
    return corrections;
  }, [rows, drafts]);

  const resolveHighlight = useCallback(
    async (sel: FieldSelection) => {
      if (!pdfDoc) return;
      const page = sel.row.source_page ?? 1;
      setPdfPage(page);
      const value = extractedValue(sel.row, sel.field) || reviewedValue(sel.row, sel.field, drafts);
      const anchorField = anchorFieldForRowType(sel.row.row_type);
      const anchorValue = anchorField ? extractedValue(sel.row, anchorField) : undefined;
      try {
        const pdfPageObj = await pdfDoc.getPage(page);
        const text = await pdfPageObj.getTextContent();
        const items = mapPdfJsTextItems(
          text.items.filter((i): i is { str: string; transform: number[]; width: number; height: number } => "str" in i),
        );
        const rect = resolveHighlightOnPage(items, {
          page,
          field: sel.field,
          label: sel.label,
          value,
          rowType: sel.row.row_type,
          sourceRowNumber: sel.row.source_row_number ?? 0,
          anchorField,
          anchorValue,
        });
        if (!rect) {
          setHighlight(null);
          return;
        }
        setHighlight({ ...rect, page });
      } catch {
        setHighlight(null);
      }
    },
    [pdfDoc, drafts],
  );

  const selectField = (row: FuelBvdRow, field: string, label: string) => {
    const sel = { rowId: row.id, field, label, row };
    setSelection(sel);
    setActiveTab(defaultTabForRowType(row.row_type));
    void resolveHighlight(sel);
  };

  const onDraft = (rowId: number, field: string, value: string) => {
    setDrafts((prev) => ({ ...prev, [draftKey(rowId, field)]: value }));
  };

  const handleSaveReview = async () => {
    if (!importId) return;
    setSaving(true);
    setActionError(null);
    try {
      await saveFuelBvdReview(importId, buildCorrectionsPayload());
      await load();
      if (selection) {
        const row = rows.find((r) => r.id === selection.rowId);
        if (row) void resolveHighlight({ ...selection, row });
      }
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const openProcessConfirm = async () => {
    if (!importId) return;
    setActionError(null);
    try {
      const pending = buildCorrectionsPayload();
      if (pending.length) {
        await saveFuelBvdReview(importId, pending);
        await load();
      }
      setConfirmSummary(await getFuelBvdImportSummary(importId));
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Could not load summary");
    }
  };

  const handleConfirmProcess = async () => {
    if (!importId) return;
    setProcessing(true);
    try {
      await processFuelBvdImport(importId);
      setConfirmSummary(null);
      await load();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Process failed");
    } finally {
      setProcessing(false);
    }
  };

  if (loading) return <div className="p-6 text-sm text-[var(--trk-text-muted)]">Loading BVD review…</div>;
  if (error) {
    return (
      <div className="p-6">
        <p className="text-sm text-[var(--trk-danger)]">{error}</p>
        <Link to={OPS.FUEL_BVD_UPLOAD} className="mt-2 inline-block text-sm text-[var(--trk-accent)]">Back to upload</Link>
      </div>
    );
  }

  const invoiceLabel = header?.invoice_number ? `Invoice ${header.invoice_number}` : "BVD review";
  const selectedRow = selection ? rows.find((r) => r.id === selection.rowId) : null;

  const renderCell = (row: FuelBvdRow, field: string, label: string) => {
    const selected = selection?.rowId === row.id && selection.field === field;
    const corrected = isFieldCorrected(row, field, drafts);
    const display = reviewedValue(row, field, drafts) || "—";
    return (
      <button
        type="button"
        onClick={() => selectField(row, field, label)}
        className={`w-full rounded px-1 py-0.5 text-left text-xs ${
          selected ? "ring-2 ring-[var(--trk-accent)] bg-[var(--trk-surface-2)]" : "hover:bg-[var(--trk-surface-2)]"
        }`}
      >
        <span className="block text-[var(--trk-text)]">{display}</span>
        {selected ? (
          <span className="mt-0.5 block">
            <FieldStatusBadge corrected={corrected} />
          </span>
        ) : corrected ? (
          <span className="mt-0.5 block text-[10px] text-[var(--trk-warning)]">Corrected</span>
        ) : null}
      </button>
    );
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col bg-[var(--trk-bg)]">
      {confirmSummary ? (
        <ProcessConfirmModal
          summary={confirmSummary}
          busy={processing}
          onCancel={() => setConfirmSummary(null)}
          onConfirm={() => void handleConfirmProcess()}
        />
      ) : null}

      <header className="flex shrink-0 items-center justify-between border-b border-[var(--trk-border)] px-4 py-2">
        <div>
          <h1 className="text-base font-semibold text-[var(--trk-text)]">BVD review</h1>
          <p className="text-xs text-[var(--trk-text-muted)]">
            {invoiceLabel} · {rows.length} source records · Status: {reviewStatusLabel(reviewStatus)}
          </p>
        </div>
        <Link to={OPS.FUEL_BVD_UPLOAD} className="text-sm text-[var(--trk-accent)]">Upload another</Link>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
        <div className="flex min-h-0 flex-col border-b border-[var(--trk-border)] lg:border-b-0 lg:border-r">
          <div className="flex items-center justify-between border-b border-[var(--trk-border)] px-3 py-2 text-xs">
            <span className="font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Original BVD PDF</span>
            <div className="flex items-center gap-2">
              <button type="button" disabled={pdfPage <= 1} onClick={() => setPdfPage((p) => p - 1)} className="rounded border border-[var(--trk-border)] px-2 py-0.5 disabled:opacity-40">‹ Previous</button>
              <span className="text-[var(--trk-text-muted)]">Page {pdfPage} of {pageCount}</span>
              <button type="button" disabled={pdfPage >= pageCount} onClick={() => setPdfPage((p) => p + 1)} className="rounded border border-[var(--trk-border)] px-2 py-0.5 disabled:opacity-40">Next ›</button>
              <button type="button" onClick={() => setPdfZoom((z) => Math.max(50, z - 10))} className="rounded border border-[var(--trk-border)] px-1.5">−</button>
              <span>{pdfZoom}%</span>
              <button type="button" onClick={() => setPdfZoom((z) => Math.min(200, z + 10))} className="rounded border border-[var(--trk-border)] px-1.5">+</button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto bg-[var(--trk-surface)] p-3">
            <BvdPdfViewer
              document={pdfDoc}
              pageNumber={pdfPage}
              zoom={pdfZoom}
              highlight={highlight}
              loading={pdfLoading}
              error={pdfError}
            />
          </div>
        </div>

        <div className="flex min-h-0 flex-col">
          <div className="flex shrink-0 gap-1 border-b border-[var(--trk-border)] px-2 py-2">
            {BVD_REVIEW_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                  activeTab === tab.id
                    ? "bg-[var(--trk-btn-primary)] text-[var(--trk-btn-text)]"
                    : "text-[var(--trk-text-muted)] hover:bg-[var(--trk-surface-2)]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {selection && selectedRow ? (
            <div className="shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-3 py-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-[var(--trk-text)]">{selection.label}</span>
                <FieldStatusBadge corrected={isFieldCorrected(selectedRow, selection.field, drafts)} />
              </div>
              <p className="mt-1 text-[var(--trk-text-muted)]">Extracted: {extractedValue(selectedRow, selection.field) || "—"}</p>
              {!readOnly ? (
                <input
                  className="mt-1 w-full rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1 text-[var(--trk-text)]"
                  value={reviewedValue(selectedRow, selection.field, drafts)}
                  onChange={(e) => onDraft(selectedRow.id, selection.field, e.target.value)}
                />
              ) : (
                <p className="mt-1 text-[var(--trk-text)]">Reviewed: {reviewedValue(selectedRow, selection.field, drafts)}</p>
              )}
              {selectedRow.field_corrections?.[selection.field] ? (
                <p className="mt-1 text-[10px] text-[var(--trk-text-muted)]">
                  Saved by {selectedRow.field_corrections[selection.field].reviewed_by ?? "—"} at{" "}
                  {selectedRow.field_corrections[selection.field].reviewed_at ?? "—"}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="shrink-0 border-b border-[var(--trk-border)] px-3 py-2 text-xs text-[var(--trk-text-muted)]">
              Select a field to verify against the PDF.
            </p>
          )}

          <div className="min-h-0 flex-1 overflow-auto p-3">
            {activeTab === "HEADER" && tabRows[0] ? (
              <dl className="grid grid-cols-[minmax(8rem,10rem)_1fr] gap-x-3 gap-y-2 text-sm">
                {BVD_HEADER_FIELDS.map((field) => {
                  if (!extractedValue(tabRows[0], field) && !persistedReviewed(tabRows[0], field)) return null;
                  return (
                    <Fragment key={field}>
                      <dt className="text-[var(--trk-text-muted)]">{BVD_FIELD_LABELS[field]}</dt>
                      <dd>{renderCell(tabRows[0], field, BVD_FIELD_LABELS[field])}</dd>
                    </Fragment>
                  );
                })}
              </dl>
            ) : null}

            {activeTab === "TRANSACTIONS" ? (
              <div className="overflow-x-auto rounded border border-[var(--trk-border)]">
                <table className="min-w-full text-left text-xs">
                  <thead className="bg-[var(--trk-surface-2)] text-[10px] uppercase text-[var(--trk-text-muted)]">
                    <tr>
                      {BVD_TRANSACTION_COLUMNS.map((c) => (
                        <th key={c.field} className="whitespace-nowrap px-2 py-1.5">{c.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tabRows.map((row) => (
                      <tr key={row.id} className="border-t border-[var(--trk-border)]">
                        {BVD_TRANSACTION_COLUMNS.map((c) => (
                          <td key={c.field} className="whitespace-nowrap px-1 py-1 align-top">
                            {renderCell(row, c.field, c.label)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            {activeTab === "CONTROLS" ? (
              <div className="space-y-4">
                {tabRows.map((row) => (
                  <div key={row.id} className="rounded border border-[var(--trk-border)] p-2">
                    <p className="mb-2 text-[10px] font-semibold uppercase text-[var(--trk-text-muted)]">
                      {row.row_type === "PAGE1_SUMMARY" ? "Page summary" : "Transaction subtotal"}
                    </p>
                    <dl className="grid grid-cols-[minmax(6rem,8rem)_1fr] gap-2 text-xs">
                      {BVD_SUBTOTAL_FIELDS.map((field) => {
                        if (!extractedValue(row, field)) return null;
                        return (
                          <Fragment key={field}>
                            <dt className="text-[var(--trk-text-muted)]">{BVD_FIELD_LABELS[field]}</dt>
                            <dd>{renderCell(row, field, BVD_FIELD_LABELS[field])}</dd>
                          </Fragment>
                        );
                      })}
                    </dl>
                  </div>
                ))}
              </div>
            ) : null}

            {activeTab === "GRAND_TOTAL" ? (
              <dl className="grid grid-cols-[minmax(8rem,10rem)_1fr] gap-2 text-sm">
                {tabRows.flatMap((row) =>
                  BVD_GRAND_TOTAL_FIELDS.map((field) => {
                    if (!extractedValue(row, field)) return null;
                    return (
                      <Fragment key={`${row.id}-${field}`}>
                        <dt className="text-[var(--trk-text-muted)]">{BVD_FIELD_LABELS[field]}</dt>
                        <dd>{renderCell(row, field, BVD_FIELD_LABELS[field])}</dd>
                      </Fragment>
                    );
                  }),
                )}
              </dl>
            ) : null}

            {activeTab === "LEGEND" ? (
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-[var(--trk-text-muted)]">
                    <th className="px-2 py-1 text-left">Code</th>
                    <th className="px-2 py-1 text-left">Product Name</th>
                  </tr>
                </thead>
                <tbody>
                  {tabRows.map((row) => (
                    <tr key={row.id} className="border-t border-[var(--trk-border)]">
                      <td className="px-2 py-1">{renderCell(row, "legend_code", "Code")}</td>
                      <td className="px-2 py-1">{renderCell(row, "legend_product_name", "Product Name")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        </div>
      </div>

      <footer className="sticky bottom-0 flex shrink-0 items-center justify-between gap-3 border-t border-[var(--trk-border)] bg-[var(--trk-surface)] px-4 py-3">
        {actionError ? (
          <p className="text-xs text-[var(--trk-danger)]">{actionError}</p>
        ) : (
          <p className="text-xs text-[var(--trk-text-muted)]">Click a value to jump to its PDF source. Corrections use the append-only overlay.</p>
        )}
        <div className="flex gap-2">
          <button type="button" disabled={readOnly || saving} onClick={() => void handleSaveReview()} className="rounded-md border border-[var(--trk-border-strong)] px-4 py-2 text-sm disabled:opacity-50">
            {saving ? "Saving…" : "Save review"}
          </button>
          <button type="button" disabled={readOnly || processing} onClick={() => void openProcessConfirm()} className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50">
            Process
          </button>
        </div>
      </footer>
    </div>
  );
}
