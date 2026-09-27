import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  fuelBvdDocumentUrl,
  getFuelBvdImportRows,
  type FuelBvdRow,
} from "../api";
import { OPS } from "../routes";
import BvdParsedStatementView from "./fuelBvdReview/BvdParsedStatementView";
import BvdPdfPopupModal from "./fuelBvdReview/BvdPdfPopupModal";
import { loadBvdPdfDocument } from "./fuelBvdReview/loadBvdPdfDocument";
import { reviewStatusLabel } from "./fuelBvdReviewLabels";

/** FULL STORED DETAIL — read-only provider projection after Process. */
export default function FuelBvdFullDetailPage() {
  const { importId } = useParams<{ importId: string }>();
  const [rows, setRows] = useState<FuelBvdRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfOpen, setPdfOpen] = useState(false);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!importId) return;
    setRows(await getFuelBvdImportRows(importId));
  }, [importId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load BVD detail"))
      .finally(() => setLoading(false));
  }, [load]);

  const reviewStatus = useMemo(() => {
    if (rows.some((r) => r.review_status === "SOURCE_REVIEWED")) return "SOURCE_REVIEWED";
    if (rows.some((r) => r.review_status === "IN_REVIEW")) return "IN_REVIEW";
    return rows.find((r) => r.row_type === "HEADER")?.review_status ?? "PENDING";
  }, [rows]);

  const header = useMemo(() => rows.find((r) => r.row_type === "HEADER"), [rows]);

  const ensurePdfLoaded = useCallback(async () => {
    if (!importId || pdfDoc) return;
    setPdfLoading(true);
    setPdfError(null);
    try {
      const url = fuelBvdDocumentUrl(importId);
      setPdfDoc(await loadBvdPdfDocument(url));
    } catch (e: unknown) {
      setPdfError(e instanceof Error ? e.message : "Could not load PDF");
    } finally {
      setPdfLoading(false);
    }
  }, [importId, pdfDoc]);

  if (loading) return <div className="p-6 text-sm text-gray-500">Loading stored detail…</div>;
  if (error || !importId) {
    return (
      <div className="p-6">
        <p className="text-sm text-red-700">{error ?? "Missing import"}</p>
        <Link to={OPS.FUEL_HISTORY} className="mt-2 inline-block text-sm text-blue-700">Back to Fuel history</Link>
      </div>
    );
  }

  const pdfTitle = header?.invoice_number ? `BVD ${header.invoice_number}` : "Original BVD PDF";

  return (
    <>
      <BvdPdfPopupModal
        open={pdfOpen}
        onClose={() => setPdfOpen(false)}
        title={pdfTitle}
        pdfDocument={pdfDoc}
        loading={pdfLoading}
        error={pdfError}
      />
      <div className="bvd-review-page">
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
          <Link to={OPS.FUEL_HISTORY} className="text-blue-700 hover:underline">← Fuel history</Link>
          <span className="text-xs text-gray-500">Full stored detail (read-only)</span>
        </div>
        <BvdParsedStatementView
          rows={rows}
          statusLabel={reviewStatusLabel(reviewStatus)}
          onOpenPdf={() => {
            setPdfOpen(true);
            void ensurePdfLoaded();
          }}
          presentation="full-stored-detail"
        />
      </div>
    </>
  );
}
