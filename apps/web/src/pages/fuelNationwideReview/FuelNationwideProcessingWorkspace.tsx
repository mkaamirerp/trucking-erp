import { useCallback, useEffect, useMemo, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  fuelNationwideDocumentUrl,
  getFuelNationwideImportRows,
  getFuelNationwideImportSummary,
  getFuelNationwideSourceReconciliation,
  processFuelNationwideImport,
  type FuelNationwideReviewSummary,
  type FuelNationwideRow,
  type FuelNationwideSourceReconciliation,
} from "../../api";
import FuelFullScreenOverlay from "../fuel/FuelFullScreenOverlay";
import BvdPdfPopupModal from "../fuelBvdReview/BvdPdfPopupModal";
import { formatFuelBvdReviewActionError } from "../fuelBvdReview/bvdReviewActionErrors";
import { loadBvdPdfDocument } from "../fuelBvdReview/loadBvdPdfDocument";
import NationwideParsedStatementView from "./NationwideParsedStatementView";
import "../fuelBvdReview/bvd-parsed-statement.css";

function NationwideProcessConfirmModal({
  summary,
  busy,
  onCancel,
  onConfirm,
}: {
  summary: FuelNationwideReviewSummary;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] p-5 shadow-xl">
        <h2 className="text-base font-semibold text-[var(--trk-text)]">Confirm process</h2>
        <p className="mt-2 text-sm text-[var(--trk-text-muted)]">
          Creates canonical fuel transactions from this Nationwide source review.
        </p>
        <dl className="mt-4 space-y-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--trk-text-muted)]">Invoice</dt>
            <dd className="font-medium text-[var(--trk-text)]">{summary.invoice_number ?? "—"}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--trk-text-muted)]">Transactions</dt>
            <dd>{summary.transaction_count}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-[var(--trk-text-muted)]">Corrections</dt>
            <dd>{summary.correction_count}</dd>
          </div>
        </dl>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-[var(--trk-border)] px-3 py-1.5 text-sm"
          >
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

export type FuelNationwideProcessingWorkspaceProps = {
  importId: string;
  variant: "overlay" | "route";
  onProcessed?: (payload: { importId: string; invoiceNumber?: string }) => void;
  onClose?: () => void;
};

export default function FuelNationwideProcessingWorkspace({
  importId,
  variant,
  onProcessed,
  onClose,
}: FuelNationwideProcessingWorkspaceProps) {
  const [rows, setRows] = useState<FuelNationwideRow[]>([]);
  const [sourceReconciliation, setSourceReconciliation] = useState<FuelNationwideSourceReconciliation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfOpen, setPdfOpen] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processOpening, setProcessOpening] = useState(false);
  const [confirmSummary, setConfirmSummary] = useState<FuelNationwideReviewSummary | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [nextRows, recon] = await Promise.all([
      getFuelNationwideImportRows(importId),
      getFuelNationwideSourceReconciliation(importId),
    ]);
    setRows(nextRows);
    setSourceReconciliation(recon);
  }, [importId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load Nationwide review"))
      .finally(() => setLoading(false));
  }, [importId, load]);

  useEffect(() => {
    if (variant !== "overlay") return;
    document.body.classList.add("fuel-overlay-open");
    return () => document.body.classList.remove("fuel-overlay-open");
  }, [variant]);

  const header = useMemo(() => rows.find((r) => r.row_type === "HEADER"), [rows]);
  const invoiceLabel = header?.invoice_number ? `Invoice ${header.invoice_number}` : "Nationwide import";

  const ensurePdfLoaded = useCallback(async () => {
    if (pdfDoc) return;
    setPdfLoading(true);
    setPdfError(null);
    try {
      setPdfDoc(await loadBvdPdfDocument(fuelNationwideDocumentUrl(importId)));
    } catch (e: unknown) {
      setPdfError(e instanceof Error ? e.message : "PDF load failed");
    } finally {
      setPdfLoading(false);
    }
  }, [importId, pdfDoc]);

  const openProcessConfirm = async () => {
    setProcessOpening(true);
    setActionError(null);
    try {
      setConfirmSummary(await getFuelNationwideImportSummary(importId));
    } catch (e: unknown) {
      setActionError(formatFuelBvdReviewActionError(e));
    } finally {
      setProcessOpening(false);
    }
  };

  const handleConfirmProcess = async () => {
    setProcessing(true);
    setActionError(null);
    try {
      const result = await processFuelNationwideImport(importId);
      setConfirmSummary(null);
      if (variant === "overlay" && onProcessed) {
        onProcessed({ importId, invoiceNumber: result.invoice_number ?? undefined });
        return;
      }
    } catch (e: unknown) {
      setConfirmSummary(null);
      setActionError(formatFuelBvdReviewActionError(e));
    } finally {
      setProcessing(false);
    }
  };

  const body = loading ? (
    <p className="p-6 text-sm text-[var(--trk-text-muted)]">Loading Nationwide review…</p>
  ) : error ? (
    <p className="p-6 text-sm text-[var(--trk-danger)]">{error}</p>
  ) : (
    <>
      <BvdPdfPopupModal
        open={pdfOpen}
        onClose={() => setPdfOpen(false)}
        title={invoiceLabel}
        pdfDocument={pdfDoc}
        loading={pdfLoading}
        error={pdfError}
      />
      {confirmSummary ? (
        <NationwideProcessConfirmModal
          summary={confirmSummary}
          busy={processing}
          onCancel={() => setConfirmSummary(null)}
          onConfirm={() => void handleConfirmProcess()}
        />
      ) : null}
      <NationwideParsedStatementView
        rows={rows}
        statusLabel="In review"
        onOpenPdf={() => {
          setPdfOpen(true);
          void ensurePdfLoaded();
        }}
        sourceReconciliation={sourceReconciliation}
      />
      <footer className="bvd-statement__footer-bar sticky bottom-0 z-20">
        <div className="flex w-full flex-wrap items-center justify-between gap-3 px-3 py-2">
          <div className="min-w-0 flex-1">
            {actionError ? (
              <p className="text-xs font-medium text-[var(--trk-danger)]" role="alert">{actionError}</p>
            ) : (
              <p className="text-xs text-[var(--trk-text-muted)]">
                Review purchases and provider controls above, then Process when ready.
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={processing || processOpening}
              onClick={() => void openProcessConfirm()}
              className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
            >
              {processOpening ? "Loading…" : processing ? "Processing…" : "Process"}
            </button>
          </div>
        </div>
      </footer>
    </>
  );

  if (variant === "overlay") {
    return (
      <FuelFullScreenOverlay
        open
        title="Fuel / Processing"
        subtitle={`Nationwide · ${invoiceLabel}`}
        onClose={onClose}
        testId="fuel-nationwide-processing-overlay"
      >
        {body}
      </FuelFullScreenOverlay>
    );
  }
  return body;
}
