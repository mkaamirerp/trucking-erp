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
import BvdReviewWorkspace, { type BvdReviewBlockers } from "./fuelBvdReview/BvdReviewWorkspace";
import { loadBvdPdfDocument } from "./fuelBvdReview/loadBvdPdfDocument";
import { draftKey, extractedValue, type DraftMap, reviewedValue } from "./fuelBvdReview/bvdReviewValues";
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
  const [drafts, setDrafts] = useState<DraftMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [confirmSummary, setConfirmSummary] = useState<FuelBvdReviewSummary | null>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [reviewBlockers, setReviewBlockers] = useState<BvdReviewBlockers>({
    unmappedCount: 0,
    possibleUnmappedCount: 0,
    unmapped: [],
    possible: [],
  });

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

  const header = useMemo(() => rows.find((r) => r.row_type === "HEADER"), [rows]);
  const reviewStatus = header?.review_status ?? "PENDING";
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
  const cardLabel = header?.card_number ? `Card ${header.card_number}` : "";

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
      <div className="flex items-center justify-end px-3 pt-1">
        <Link to={OPS.FUEL_BVD_UPLOAD} className="text-xs text-[var(--trk-accent)]">Upload another</Link>
      </div>
      <BvdReviewWorkspace
        pdfDocument={pdfDoc}
        rows={rows}
        drafts={drafts}
        onDraft={onDraft}
        readOnly={readOnly}
        invoiceLabel={invoiceLabel}
        cardLabel={cardLabel}
        statusLabel={reviewStatusLabel(reviewStatus)}
        pdfLoading={pdfLoading}
        pdfError={pdfError}
        onReviewBlockersChange={setReviewBlockers}
        footer={
          <div className="flex items-center justify-between gap-3">
            {actionError ? (
              <p className="text-xs text-[var(--trk-danger)]">{actionError}</p>
            ) : reviewBlockers.unmappedCount > 0 ? (
              <p className="text-xs text-[var(--trk-warning)]">
                Process blocked: {reviewBlockers.unmappedCount} unmapped source field
                {reviewBlockers.unmappedCount === 1 ? "" : "s"} require review (backend guard recommended).
              </p>
            ) : (
              <p className="text-xs text-[var(--trk-text-muted)]">Side-by-side source review. Tab moves field order.</p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                disabled={readOnly || saving}
                onClick={() => void handleSaveReview()}
                className="rounded-md border border-[var(--trk-border-strong)] px-4 py-2 text-sm disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save review"}
              </button>
              <button
                type="button"
                disabled={readOnly || processing || reviewBlockers.unmappedCount > 0}
                title={
                  reviewBlockers.unmappedCount > 0
                    ? `${reviewBlockers.unmappedCount} unmapped source field(s) must be reviewed first`
                    : undefined
                }
                onClick={() => void openProcessConfirm()}
                className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
              >
                Process
              </button>
            </div>
          </div>
        }
      />
    </>
  );
}
