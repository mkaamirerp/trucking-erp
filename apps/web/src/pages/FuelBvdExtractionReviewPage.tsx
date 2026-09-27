import { useCallback, useEffect, useMemo, useState } from "react";
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
import BvdParsedStatementView from "./fuelBvdReview/BvdParsedStatementView";
import BvdPdfPopupModal from "./fuelBvdReview/BvdPdfPopupModal";
import { loadBvdPdfDocument } from "./fuelBvdReview/loadBvdPdfDocument";
import { draftKey, extractedValue, type DraftMap, reviewedValue } from "./fuelBvdReview/bvdReviewValues";
import { formatFuelBvdReviewActionError } from "./fuelBvdReview/bvdReviewActionErrors";
import { buildBvdUploadCompletedPath } from "./fuelBvdReview/bvdUploadCompletion";
import { BVD_FIELD_LABELS, reviewStatusLabel } from "./fuelBvdReviewLabels";

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

export default function FuelBvdExtractionReviewPage() {
  const { importId } = useParams();
  const [rows, setRows] = useState<FuelBvdRow[]>([]);
  const [drafts] = useState<DraftMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processOpening, setProcessOpening] = useState(false);
  const [confirmSummary, setConfirmSummary] = useState<FuelBvdReviewSummary | null>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfOpen, setPdfOpen] = useState(false);
  const [showCompletedStatement, setShowCompletedStatement] = useState(false);

  const load = useCallback(async () => {
    if (!importId) return;
    setRows(await getFuelBvdImportRows(importId));
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

  const ensurePdfLoaded = useCallback(async () => {
    if (!importId || pdfDoc) return;
    setPdfLoading(true);
    setPdfError(null);
    try {
      setPdfDoc(await loadBvdPdfDocument(fuelBvdDocumentUrl(importId)));
    } catch (e: unknown) {
      setPdfError(e instanceof Error ? e.message : "PDF load failed");
    } finally {
      setPdfLoading(false);
    }
  }, [importId, pdfDoc]);

  const openPdf = () => {
    setPdfOpen(true);
    void ensurePdfLoaded();
  };

  const header = useMemo(() => rows.find((r) => r.row_type === "HEADER"), [rows]);
  const reviewStatus = useMemo(() => {
    if (rows.some((r) => r.review_status === "SOURCE_REVIEWED")) {
      return "SOURCE_REVIEWED";
    }
    if (rows.some((r) => r.review_status === "IN_REVIEW")) {
      return "IN_REVIEW";
    }
    return header?.review_status ?? "PENDING";
  }, [rows, header]);
  const readOnly = reviewStatus === "SOURCE_REVIEWED";

  const buildCorrectionsPayload = useCallback(() => {
    const corrections: { fuel_bvd_id: number; field_name: string; reviewed_value: string }[] = [];
    for (const row of rows) {
      const fields = new Set<string>();
      Object.keys(BVD_FIELD_LABELS).forEach((f) => {
        if (extractedValue(row, f) || drafts[draftKey(row.id, f)]) fields.add(f);
      });
      for (const field of fields) {
        const ext = extractedValue(row, field);
        const rev = reviewedValue(row, field, drafts);
        if (rev !== ext) corrections.push({ fuel_bvd_id: row.id, field_name: field, reviewed_value: rev });
      }
    }
    return corrections;
  }, [rows, drafts]);

  const handleSaveReview = async () => {
    if (!importId || readOnly) return;
    setSaving(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const result = await saveFuelBvdReview(importId, buildCorrectionsPayload());
      await load();
      setActionSuccess(
        result.saved_corrections > 0
          ? `Review saved (${result.saved_corrections} correction${result.saved_corrections === 1 ? "" : "s"})`
          : "Review saved",
      );
    } catch (e: unknown) {
      setActionError(formatFuelBvdReviewActionError(e));
    } finally {
      setSaving(false);
    }
  };

  const openProcessConfirm = async () => {
    if (!importId || readOnly) return;
    setProcessOpening(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const pending = buildCorrectionsPayload();
      if (pending.length) {
        await saveFuelBvdReview(importId, pending);
        await load();
      }
      setConfirmSummary(await getFuelBvdImportSummary(importId));
    } catch (e: unknown) {
      setActionError(formatFuelBvdReviewActionError(e));
    } finally {
      setProcessOpening(false);
    }
  };

  const handleConfirmProcess = async () => {
    if (!importId) return;
    setProcessing(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const result = await processFuelBvdImport(importId);
      setConfirmSummary(null);
      window.location.assign(buildBvdUploadCompletedPath(result.invoice_number));
      return;
    } catch (e: unknown) {
      setConfirmSummary(null);
      setActionError(formatFuelBvdReviewActionError(e));
    } finally {
      setProcessing(false);
    }
  };

  if (loading) return <div className="p-6 text-sm text-[var(--trk-text-muted)]">Loading BVD…</div>;
  if (error) {
    return (
      <div className="p-6">
        <p className="text-sm text-[var(--trk-danger)]">{error}</p>
        <Link to={OPS.FUEL_BVD_UPLOAD} className="mt-2 inline-block text-sm text-[var(--trk-accent)]">Back to upload</Link>
      </div>
    );
  }

  const pdfTitle = header?.invoice_number ? `BVD ${header.invoice_number}` : "Original BVD PDF";

  if (readOnly && !showCompletedStatement) {
    return (
      <div className="mx-auto max-w-lg px-4 py-10">
        <div
          role="status"
          className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] px-5 py-6 shadow-sm"
        >
          <h1 className="text-lg font-semibold text-[var(--trk-text)]">BVD source review completed</h1>
          <p className="mt-2 text-sm text-[var(--trk-text-muted)]">
            {header?.invoice_number ? `Invoice ${header.invoice_number} ` : "This import "}
            is marked completed. BVD reviews are finished here — they do not appear on{" "}
            <Link to={OPS.FUEL_REVIEW} className="text-[var(--trk-accent)] hover:underline">
              Fuel source review
            </Link>{" "}
            (that queue is for separate provider import batches).
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            {importId ? (
              <Link
                to={OPS.FUEL_BVD_DETAIL(importId)}
                className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)]"
              >
                Full stored detail
              </Link>
            ) : null}
            <Link
              to={OPS.FUEL_HISTORY}
              className="rounded-md border border-[var(--trk-border-strong)] px-4 py-2 text-sm"
            >
              Fuel history
            </Link>
            <button
              type="button"
              onClick={() => setShowCompletedStatement(true)}
              className="rounded-md border border-[var(--trk-border-strong)] px-4 py-2 text-sm"
            >
              View parsed statement
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      {confirmSummary ? (
        <ProcessConfirmModal
          summary={confirmSummary}
          busy={processing}
          onCancel={() => setConfirmSummary(null)}
          onConfirm={() => void handleConfirmProcess()}
        />
      ) : null}
      <BvdPdfPopupModal
        open={pdfOpen}
        onClose={() => setPdfOpen(false)}
        title={pdfTitle}
        pdfDocument={pdfDoc}
        loading={pdfLoading}
        error={pdfError}
      />
      <div className="bvd-review-page">
        <div className="flex items-center justify-end px-3 py-1">
          <Link to={OPS.FUEL_BVD_UPLOAD} className="text-xs text-[var(--trk-accent)]">Upload another</Link>
        </div>
        {readOnly ? (
          <div
            role="status"
            className="mx-3 mb-2 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-4 py-3 text-sm"
          >
            <p className="font-medium text-[var(--trk-text)]">BVD source review completed</p>
            <p className="mt-1 text-xs text-[var(--trk-text-muted)]">
              This invoice is marked completed here. Fuel source review lists separate provider import batches — BVD
              uploads do not appear in that queue.
            </p>
            <Link to={OPS.FUEL_BVD_UPLOAD} className="mt-2 inline-block text-xs font-medium text-[var(--trk-accent)]">
              Upload another BVD
            </Link>
          </div>
        ) : null}
        <BvdParsedStatementView
          rows={rows}
          statusLabel={reviewStatusLabel(reviewStatus)}
          onOpenPdf={openPdf}
        />
        <footer className="bvd-statement__footer-bar sticky bottom-0 z-20">
          <div className="flex w-full flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              {actionError ? (
                <p className="text-xs font-medium text-[var(--trk-danger)]" role="alert">
                  {actionError}
                </p>
              ) : actionSuccess ? (
                <p className="text-xs font-medium text-[var(--trk-success)]" role="status">
                  {actionSuccess}
                </p>
              ) : (
                <p className="text-xs text-[var(--trk-text-muted)]">
                  Parsed BVD view — open PDF to compare against the original document.
                </p>
              )}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={readOnly || saving || processing || processOpening}
                onClick={() => void handleSaveReview()}
                className="rounded-md border border-[var(--trk-border-strong)] px-4 py-2 text-sm disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save review"}
              </button>
              <button
                type="button"
                disabled={readOnly || saving || processing || processOpening}
                onClick={() => void openProcessConfirm()}
                className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
              >
                {processOpening ? "Loading…" : processing ? "Processing…" : readOnly ? "Completed" : "Process"}
              </button>
            </div>
          </div>
        </footer>
      </div>
    </>
  );
}
