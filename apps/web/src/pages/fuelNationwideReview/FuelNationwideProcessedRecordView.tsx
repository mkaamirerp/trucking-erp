import { useCallback, useEffect, useMemo, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  fuelNationwideDocumentUrl,
  getFuelNationwideImportRows,
  getFuelNationwideSourceReconciliation,
  type FuelNationwideRow,
  type FuelNationwideSourceReconciliation,
} from "../../api";
import FuelFullScreenOverlay from "../fuel/FuelFullScreenOverlay";
import BvdPdfPopupModal from "../fuelBvdReview/BvdPdfPopupModal";
import { loadBvdPdfDocument } from "../fuelBvdReview/loadBvdPdfDocument";
import NationwideParsedStatementView from "./NationwideParsedStatementView";
import "../fuelBvdReview/bvd-parsed-statement.css";

export type FuelNationwideProcessedRecordViewProps = {
  importId: string;
  variant: "overlay" | "route";
  onClose?: () => void;
};

export default function FuelNationwideProcessedRecordView({
  importId,
  variant,
  onClose,
}: FuelNationwideProcessedRecordViewProps) {
  const [rows, setRows] = useState<FuelNationwideRow[]>([]);
  const [sourceReconciliation, setSourceReconciliation] = useState<FuelNationwideSourceReconciliation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfOpen, setPdfOpen] = useState(false);

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
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load Nationwide detail"))
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

  const body = loading ? (
    <p className="p-6 text-sm text-[var(--trk-text-muted)]">Loading processed Nationwide invoice…</p>
  ) : error ? (
    <p className="p-6 text-sm text-[var(--trk-danger)]">{error}</p>
  ) : (
    <div
      className="fuel-processed-record flex min-h-0 flex-1 flex-col"
      data-testid="fuel-nationwide-processed-record"
      data-transaction-count={rows.filter((r) => r.row_type === "TRANSACTION").length}
      data-control-count={rows.filter((r) => r.row_type === "CONTROL").length}
    >
      <BvdPdfPopupModal
        open={pdfOpen}
        onClose={() => setPdfOpen(false)}
        title={invoiceLabel}
        pdfDocument={pdfDoc}
        loading={pdfLoading}
        error={pdfError}
      />
      <NationwideParsedStatementView
        rows={rows}
        statusLabel="Processed"
        onOpenPdf={() => {
          setPdfOpen(true);
          void ensurePdfLoaded();
        }}
        sourceReconciliation={sourceReconciliation}
      />
      <footer className="bvd-statement__footer-bar sticky bottom-0 z-20 px-3 py-2">
        <p className="text-xs text-[var(--trk-text-muted)]">
          Processed Nationwide source record — read-only. No staging corrections or Process actions.
        </p>
      </footer>
    </div>
  );

  if (variant === "overlay") {
    return (
      <FuelFullScreenOverlay
        open
        title="Fuel / Processed"
        subtitle={`Nationwide · ${invoiceLabel}`}
        onClose={onClose}
        testId="fuel-nationwide-processed-overlay"
      >
        {body}
      </FuelFullScreenOverlay>
    );
  }
  return body;
}
