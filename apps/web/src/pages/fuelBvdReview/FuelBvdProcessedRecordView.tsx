import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  fuelBvdDocumentUrl,
  getFuelBvdImportRows,
  getFuelBvdSourceReconciliation,
  type FuelBvdRow,
  type FuelBvdSourceReconciliation,
} from "../../api";
import { OPS } from "../../routes";
import FuelFullScreenOverlay from "../fuel/FuelFullScreenOverlay";
import BvdParsedStatementView from "./BvdParsedStatementView";
import BvdPdfPopupModal from "./BvdPdfPopupModal";
import { loadBvdPdfDocument } from "./loadBvdPdfDocument";
import { reviewStatusLabel } from "../fuelBvdReviewLabels";
import "./bvd-parsed-statement.css";

export type FuelBvdProcessedRecordViewProps = {
  importId: string;
  variant: "overlay" | "route";
  onClose?: () => void;
};

export default function FuelBvdProcessedRecordView({
  importId,
  variant,
  onClose,
}: FuelBvdProcessedRecordViewProps) {
  const [rows, setRows] = useState<FuelBvdRow[]>([]);
  const [sourceReconciliation, setSourceReconciliation] = useState<FuelBvdSourceReconciliation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfOpen, setPdfOpen] = useState(false);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

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
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load BVD detail"))
      .finally(() => setLoading(false));
  }, [importId, load]);

  useEffect(() => {
    if (variant !== "overlay") return;
    document.body.classList.add("fuel-overlay-open");
    return () => document.body.classList.remove("fuel-overlay-open");
  }, [variant]);

  const reviewStatus = useMemo(() => {
    if (rows.some((r) => r.review_status === "SOURCE_REVIEWED")) return "SOURCE_REVIEWED";
    if (rows.some((r) => r.review_status === "IN_REVIEW")) return "IN_REVIEW";
    return rows.find((r) => r.row_type === "HEADER")?.review_status ?? "PENDING";
  }, [rows]);

  const header = useMemo(() => rows.find((r) => r.row_type === "HEADER"), [rows]);
  const correctionCount = useMemo(
    () => rows.reduce((n, r) => n + Object.keys(r.field_corrections ?? {}).length, 0),
    [rows],
  );

  const ensurePdfLoaded = useCallback(async () => {
    if (pdfDoc) return;
    setPdfLoading(true);
    setPdfError(null);
    try {
      setPdfDoc(await loadBvdPdfDocument(fuelBvdDocumentUrl(importId)));
    } catch (e: unknown) {
      setPdfError(e instanceof Error ? e.message : "Could not load PDF");
    } finally {
      setPdfLoading(false);
    }
  }, [importId, pdfDoc]);

  const invoiceLabel = header?.invoice_number ? `Invoice ${header.invoice_number}` : "BVD import";
  const overlaySubtitle = `BVD · ${invoiceLabel} · Read-only`;
  const pdfTitle = header?.invoice_number ? `BVD ${header.invoice_number}` : "Original BVD PDF";

  const handleClose = () => onClose?.();

  if (loading) {
    const msg = <div className="p-6 text-sm text-[var(--trk-text-muted)]">Loading processed record…</div>;
    if (variant === "overlay") {
      return (
        <FuelFullScreenOverlay
          open
          title="Fuel / Processed record"
          subtitle="Loading…"
          onClose={handleClose}
          testId="fuel-processed-overlay"
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
        <FuelFullScreenOverlay open title="Fuel / Processed record" onClose={handleClose} testId="fuel-processed-overlay">
          {err}
        </FuelFullScreenOverlay>
      );
    }
    return err;
  }

  const recordBody = (
    <>
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
            ? "bvd-review-page fuel-processed-record"
            : "fuel-processed-record flex min-h-0 flex-1 flex-col"
        }
        data-testid="fuel-processed-record"
      >
        {variant === "route" ? (
          <div className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
            <div>
              <Link to={OPS.FUEL} className="text-xs font-medium text-[var(--trk-accent)] hover:underline">
                ← Back to Fuel
              </Link>
              <h1 className="text-sm font-semibold text-[var(--trk-text)]">Processed record</h1>
              <p className="text-xs text-[var(--trk-text-muted)]">
                Read-only · {invoiceLabel} · Status {reviewStatusLabel(reviewStatus)}
                {correctionCount > 0 ? ` · ${correctionCount} corrected field(s) on file` : ""}
              </p>
            </div>
            <span className="rounded bg-[var(--trk-surface-2)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--trk-text-muted)]">
              Immutable source
            </span>
          </div>
        ) : (
          <div className="border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-xs text-[var(--trk-text-muted)]">
            Read-only · Status {reviewStatusLabel(reviewStatus)}
            {correctionCount > 0 ? ` · ${correctionCount} corrected field(s) on file` : ""}
          </div>
        )}
        <BvdParsedStatementView
          rows={rows}
          statusLabel={reviewStatusLabel(reviewStatus)}
          onOpenPdf={() => {
            setPdfOpen(true);
            void ensurePdfLoaded();
          }}
          presentation="full-stored-detail"
          sourceReconciliation={sourceReconciliation}
        />
      </div>
    </>
  );

  if (variant === "overlay") {
    return (
      <FuelFullScreenOverlay
        open
        title="Fuel / Processed record"
        subtitle={overlaySubtitle}
        onClose={handleClose}
        testId="fuel-processed-overlay"
      >
        {recordBody}
      </FuelFullScreenOverlay>
    );
  }

  return recordBody;
}
