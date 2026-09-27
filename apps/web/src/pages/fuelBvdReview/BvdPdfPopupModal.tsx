import { useCallback, useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import BvdPdfPagePane from "./BvdPdfPagePane";
import { BVD_PDF_ZOOM_DEFAULT } from "./bvdPdfConstants";

const PANEL_WIDTH = 520;
const PANEL_MAX_H = "min(85vh, 720px)";

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  pdfDocument: PDFDocumentProxy | null;
  loading: boolean;
  error: string | null;
};

function defaultPosition(): { x: number; y: number } {
  const margin = 16;
  const x = Math.max(margin, window.innerWidth - PANEL_WIDTH - margin);
  const y = margin + 48;
  return { x, y };
}

export default function BvdPdfPopupModal({ open, onClose, title, pdfDocument, loading, error }: Props) {
  const [page, setPage] = useState(1);
  const [pos, setPos] = useState(defaultPosition);
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const pageCount = pdfDocument?.numPages ?? 1;

  useEffect(() => {
    if (!open) return;
    setPage(1);
    setPos(defaultPosition());
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const clampPosition = useCallback((x: number, y: number) => {
    const margin = 8;
    const maxX = Math.max(margin, window.innerWidth - PANEL_WIDTH - margin);
    const maxY = Math.max(margin, window.innerHeight - 120);
    return {
      x: Math.min(Math.max(margin, x), maxX),
      y: Math.min(Math.max(margin, y), maxY),
    };
  }, []);

  const onDragPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest("button")) return;
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: pos.x,
      origY: pos.y,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onDragPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    const next = clampPosition(
      dragRef.current.origX + (e.clientX - dragRef.current.startX),
      dragRef.current.origY + (e.clientY - dragRef.current.startY),
    );
    setPos(next);
  };

  const onDragPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* already released */
    }
  };

  if (!open) return null;

  return (
    <div className="bvd-pdf-float" aria-label="Original BVD PDF (floating)">
      <div
        className="bvd-pdf-modal__panel bvd-pdf-modal__panel--floating"
        style={{ left: pos.x, top: pos.y, width: PANEL_WIDTH, maxHeight: PANEL_MAX_H }}
        role="dialog"
      >
        <div
          className="bvd-pdf-modal__head bvd-pdf-modal__head--drag"
          onPointerDown={onDragPointerDown}
          onPointerMove={onDragPointerMove}
          onPointerUp={onDragPointerUp}
          onPointerCancel={onDragPointerUp}
        >
          <div className="min-w-0 flex-1">
            <span className="block truncate font-medium text-[var(--trk-text)]">{title}</span>
            <span className="text-[10px] text-[var(--trk-text-muted)]">Drag here to move · statement stays clickable below</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded border border-[var(--trk-border)] px-2 py-0.5 text-xs disabled:opacity-40"
            >
              Prev
            </button>
            <span className="text-xs text-[var(--trk-text-muted)] whitespace-nowrap">
              {page} / {pageCount}
            </span>
            <button
              type="button"
              disabled={page >= pageCount}
              onClick={() => setPage((p) => p + 1)}
              className="rounded border border-[var(--trk-border)] px-2 py-0.5 text-xs disabled:opacity-40"
            >
              Next
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-[var(--trk-border)] px-2 py-0.5 text-xs"
            >
              Close
            </button>
          </div>
        </div>
        <div className="bvd-pdf-modal__body">
          {loading ? <p className="p-4 text-sm text-[var(--trk-text-muted)]">Loading PDF…</p> : null}
          {error ? <p className="p-4 text-sm text-[var(--trk-danger)]">{error}</p> : null}
          {!loading && !error && pdfDocument ? (
            <BvdPdfPagePane pdfDocument={pdfDocument} pageNumber={page} zoomPercent={BVD_PDF_ZOOM_DEFAULT} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
