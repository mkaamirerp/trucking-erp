import { useCallback, useEffect, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  fuelNationwideDocumentUrl,
  getFuelNationwideImportRows,
  getFuelNationwideSourceReconciliation,
} from "../../api";
import BvdPdfPopupModal from "../fuelBvdReview/BvdPdfPopupModal";
import { loadBvdPdfDocument } from "../fuelBvdReview/loadBvdPdfDocument";
import NationwideParsedStatementView from "../fuelNationwideReview/NationwideParsedStatementView";

type Props = {
  batchId: number;
  sourceImportRef: string | null;
  invoiceNumber: string;
  onOpenFull?: () => void;
};

export default function NationwideProcessedEvidencePanel({ sourceImportRef, onOpenFull }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Awaited<ReturnType<typeof getFuelNationwideImportRows>>>([]);
  const [reconciliation, setReconciliation] = useState<
    Awaited<ReturnType<typeof getFuelNationwideSourceReconciliation>> | null
  >(null);
  const [pdfOpen, setPdfOpen] = useState(false);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  useEffect(() => {
    if (!sourceImportRef) {
      setError("Source import reference missing");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    void Promise.all([
      getFuelNationwideImportRows(sourceImportRef),
      getFuelNationwideSourceReconciliation(sourceImportRef),
    ])
      .then(([nationwideRows, nationwideReconciliation]) => {
        setRows(nationwideRows);
        setReconciliation(nationwideReconciliation);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load Nationwide statement"))
      .finally(() => setLoading(false));
  }, [sourceImportRef]);

  const openPdf = useCallback(async () => {
    if (!sourceImportRef) return;
    setPdfOpen(true);
    if (pdfDoc) return;
    setPdfLoading(true);
    setPdfError(null);
    try {
      setPdfDoc(await loadBvdPdfDocument(fuelNationwideDocumentUrl(sourceImportRef)));
    } catch (e: unknown) {
      setPdfError(e instanceof Error ? e.message : "PDF load failed");
    } finally {
      setPdfLoading(false);
    }
  }, [pdfDoc, sourceImportRef]);

  if (loading) {
    return <p className="text-xs text-[var(--trk-text-muted)]">Loading source evidence…</p>;
  }
  if (error) {
    return <p className="text-xs text-[var(--trk-danger)]" role="alert">{error}</p>;
  }
  if (!rows.length) {
    return <p className="text-xs text-[var(--trk-text-muted)]">No source rows for this invoice.</p>;
  }

  const header = rows.find((r) => r.row_type === "HEADER");
  const invoiceLabel = header?.invoice_number ? `Invoice ${header.invoice_number}` : "Nationwide import";

  return (
    <div data-testid="nationwide-source-evidence-panel">
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
        onOpenPdf={() => void openPdf()}
        sourceReconciliation={reconciliation}
      />
      {onOpenFull ? (
        <button
          type="button"
          className="mt-2 text-xs font-medium text-[var(--trk-accent)] hover:underline"
          onClick={onOpenFull}
        >
          Open full invoice
        </button>
      ) : null}
    </div>
  );
}
