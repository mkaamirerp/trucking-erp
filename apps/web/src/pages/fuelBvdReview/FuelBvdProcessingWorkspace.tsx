import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  fuelBvdDocumentUrl,
  getFuelBvdImportRows,
  getFuelBvdImportSummary,
  getFuelBvdSourceReconciliation,
  processFuelBvdImport,
  saveFuelBvdReview,
  type FuelBvdReviewSummary,
  type FuelBvdRow,
  type FuelBvdSourceReconciliation,
} from "../../api";
import { OPS } from "../../routes";
import FuelFullScreenOverlay from "../fuel/FuelFullScreenOverlay";
import BvdParsedStatementView from "./BvdParsedStatementView";
import BvdPdfPopupModal from "./BvdPdfPopupModal";
import BvdReviewCorrectionsPanel from "./BvdReviewCorrectionsPanel";
import { loadBvdPdfDocument } from "./loadBvdPdfDocument";
import { buildFuelProcessedReturnPath } from "./bvdUploadCompletion";
import {
  draftKey,
  extractedValue,
  type DraftMap,
  reviewedValue,
} from "./bvdReviewValues";
import { formatFuelBvdReviewActionError } from "./bvdReviewActionErrors";
import { BVD_FIELD_LABELS, reviewStatusLabel } from "../fuelBvdReviewLabels";
import "./bvd-parsed-statement.css";

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
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
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

export function buildCorrectionsPayload(rows: FuelBvdRow[], drafts: DraftMap) {
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
}

export function hasUnsavedReviewDrafts(rows: FuelBvdRow[], drafts: DraftMap): boolean {
  return buildCorrectionsPayload(rows, drafts).length > 0;
}

export type FuelBvdProcessingWorkspaceProps = {
  importId: string;
  variant: "overlay" | "route";
  onProcessed?: (payload: { importId: string; invoiceNumber?: string }) => void;
  onClose?: () => void;
};

export default function FuelBvdProcessingWorkspace({
  importId,
  variant,
  onProcessed,
  onClose,
}: FuelBvdProcessingWorkspaceProps) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<FuelBvdRow[]>([]);
  const [sourceReconciliation, setSourceReconciliation] = useState<FuelBvdSourceReconciliation | null>(null);
  const [drafts, setDrafts] = useState<DraftMap>({});
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

  const load = useCallback(async () => {
    const [nextRows, recon] = await Promise.all([
      getFuelBvdImportRows(importId),
      getFuelBvdSourceReconciliation(importId),
    ]);
    setRows(nextRows);
    setSourceReconciliation(recon);
  }, [importId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load BVD review"))
      .finally(() => setLoading(false));
  }, [importId, load]);

  useEffect(() => {
    if (variant !== "overlay") return;
    document.body.classList.add("fuel-overlay-open");
    return () => document.body.classList.remove("fuel-overlay-open");
  }, [variant]);

  const ensurePdfLoaded = useCallback(async () => {
    if (pdfDoc) return;
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
    if (rows.some((r) => r.review_status === "SOURCE_REVIEWED")) return "SOURCE_REVIEWED";
    if (rows.some((r) => r.review_status === "IN_REVIEW")) return "IN_REVIEW";
    return header?.review_status ?? "PENDING";
  }, [rows, header]);
  const readOnly = reviewStatus === "SOURCE_REVIEWED";

  const onDraft = useCallback((rowId: number, field: string, value: string) => {
    setDrafts((prev) => ({ ...prev, [draftKey(rowId, field)]: value }));
  }, []);

  const handleInlineCommit = async (rowId: number, field: string, value: string) => {
    if (readOnly) return;
    setSaving(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      await saveFuelBvdReview(importId, [
        { fuel_bvd_id: rowId, field_name: field, reviewed_value: value },
      ]);
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[draftKey(rowId, field)];
        return next;
      });
      await load();
      setActionSuccess("Review saved — validations refreshed");
    } catch (e: unknown) {
      setActionError(formatFuelBvdReviewActionError(e));
    } finally {
      setSaving(false);
    }
  };

  const handleSaveReview = async () => {
    if (readOnly) return;
    setSaving(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const result = await saveFuelBvdReview(importId, buildCorrectionsPayload(rows, drafts));
      setDrafts({});
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
    if (readOnly) return;
    setProcessOpening(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const pending = buildCorrectionsPayload(rows, drafts);
      if (pending.length) {
        await saveFuelBvdReview(importId, pending);
        setDrafts({});
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
    setProcessing(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const result = await processFuelBvdImport(importId);
      setConfirmSummary(null);
      if (variant === "overlay" && onProcessed) {
        onProcessed({ importId, invoiceNumber: result.invoice_number });
        return;
      }
      navigate(buildFuelProcessedReturnPath(result.invoice_number), { replace: true });
    } catch (e: unknown) {
      setConfirmSummary(null);
      setActionError(formatFuelBvdReviewActionError(e));
    } finally {
      setProcessing(false);
    }
  };

  const requestClose = () => {
    if (!onClose) return;
    if (hasUnsavedReviewDrafts(rows, drafts)) {
      const ok = window.confirm(
        "You have unsaved review changes. Close without saving?",
      );
      if (!ok) return;
    }
    onClose();
  };

  if (loading) {
    const msg = <div className="p-6 text-sm text-[var(--trk-text-muted)]">Loading processing workspace…</div>;
    if (variant === "overlay") {
      return (
        <FuelFullScreenOverlay
          open
          title="Fuel / Processing"
          subtitle="Loading…"
          onClose={requestClose}
          testId="fuel-processing-overlay"
        >
          {msg}
        </FuelFullScreenOverlay>
      );
    }
    return msg;
  }

  if (error) {
    const err = (
      <div className="p-6">
        <p className="text-sm text-[var(--trk-danger)]">{error}</p>
        {variant === "route" ? (
          <Link to={OPS.FUEL} className="mt-2 inline-block text-sm text-[var(--trk-accent)]">Back to Fuel</Link>
        ) : null}
      </div>
    );
    if (variant === "overlay") {
      return (
        <FuelFullScreenOverlay
          open
          title="Fuel / Processing"
          onClose={requestClose}
          testId="fuel-processing-overlay"
        >
          {err}
        </FuelFullScreenOverlay>
      );
    }
    return err;
  }

  const invoiceLabel = header?.invoice_number ? `Invoice ${header.invoice_number}` : "BVD import";
  const overlaySubtitle = `BVD · ${invoiceLabel}`;
  const pdfTitle = header?.invoice_number ? `BVD ${header.invoice_number}` : "Original BVD PDF";

  const workspaceBody = (
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
      <div
        className={
          variant === "route"
            ? "bvd-review-page fuel-processing-workspace"
            : "fuel-processing-workspace flex min-h-0 flex-1 flex-col"
        }
        data-testid="fuel-processing-workspace"
      >
        {variant === "route" ? (
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
            <div>
              <Link to={OPS.FUEL} className="text-xs text-[var(--trk-accent)] hover:underline">← Back to Fuel</Link>
              <h1 className="text-sm font-semibold text-[var(--trk-text)]">Processing workspace</h1>
              <p className="text-xs text-[var(--trk-text-muted)]">
                {invoiceLabel} · Review, correct, reconcile, then Process
              </p>
            </div>
          </div>
        ) : null}
        <BvdParsedStatementView
          rows={rows}
          statusLabel={reviewStatusLabel(reviewStatus)}
          onOpenPdf={openPdf}
          drafts={drafts}
          sourceReconciliation={sourceReconciliation}
          readOnly={readOnly}
          onInlineCommit={handleInlineCommit}
        />
        <BvdReviewCorrectionsPanel rows={rows} drafts={drafts} readOnly={readOnly} onDraft={onDraft} />
        <footer className="bvd-statement__footer-bar sticky bottom-0 z-20">
          <div className="flex w-full flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              {actionError ? (
                <p className="text-xs font-medium text-[var(--trk-danger)]" role="alert">{actionError}</p>
              ) : actionSuccess ? (
                <p className="text-xs font-medium text-[var(--trk-success)]" role="status">{actionSuccess}</p>
              ) : (
                <p className="text-xs text-[var(--trk-text-muted)]">
                  Full provider fields above · PDF on demand · corrections below
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
                {processOpening ? "Loading…" : processing ? "Processing…" : "Process"}
              </button>
            </div>
          </div>
        </footer>
      </div>
    </>
  );

  if (variant === "overlay") {
    return (
      <FuelFullScreenOverlay
        open
        title="Fuel / Processing"
        subtitle={overlaySubtitle}
        onClose={requestClose}
        testId="fuel-processing-overlay"
      >
        {workspaceBody}
      </FuelFullScreenOverlay>
    );
  }

  return workspaceBody;
}
