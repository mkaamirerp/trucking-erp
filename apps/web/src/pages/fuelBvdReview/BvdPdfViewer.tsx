import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PdfHighlightRect } from "./bvdPdfHighlight";

type Props = {
  document: PDFDocumentProxy | null;
  pageNumber: number;
  zoom: number;
  highlight: PdfHighlightRect | null;
  loading?: boolean;
  error?: string | null;
};

export default function BvdPdfViewer({ document, pageNumber, zoom, highlight, loading, error }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  const [overlay, setOverlay] = useState<{ left: number; top: number; width: number; height: number } | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    async function renderPage() {
      if (!document || !canvasRef.current) return;
      const page = await document.getPage(pageNumber);
      if (cancelled) return;
      const scale = zoom / 100;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      setViewportSize({ width: viewport.width, height: viewport.height });
      await page.render({ canvasContext: ctx, viewport }).promise;
      if (cancelled) return;

      if (highlight && highlight.page === pageNumber && !highlight.ambiguous) {
        const [vx1, vy1, vx2, vy2] = viewport.convertToViewportRectangle([
          highlight.x,
          highlight.y,
          highlight.x + highlight.width,
          highlight.y + highlight.height,
        ]);
        setOverlay({
          left: Math.min(vx1, vx2),
          top: Math.min(vy1, vy2),
          width: Math.abs(vx2 - vx1),
          height: Math.abs(vy2 - vy1),
        });
        requestAnimationFrame(() => {
          const el = wrapRef.current?.querySelector("[data-bvd-highlight]");
          el?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
        });
      } else {
        setOverlay(null);
      }
    }
    void renderPage();
    return () => {
      cancelled = true;
    };
  }, [document, pageNumber, zoom, highlight]);

  if (error) {
    return <div className="p-4 text-sm text-[var(--trk-danger)]">{error}</div>;
  }
  if (loading) {
    return <div className="p-4 text-sm text-[var(--trk-text-muted)]">Loading PDF…</div>;
  }

  return (
    <div ref={wrapRef} className="relative inline-block min-w-full">
      <canvas ref={canvasRef} className="mx-auto block bg-white shadow-sm" style={{ maxWidth: "100%" }} />
      {overlay ? (
        <div
          data-bvd-highlight
          className="pointer-events-none absolute rounded border-2 border-[var(--trk-warning)] bg-[var(--trk-warning)]/25"
          style={{
            left: overlay.left,
            top: overlay.top,
            width: overlay.width,
            height: overlay.height,
          }}
        />
      ) : null}
      {highlight?.ambiguous ? (
        <p className="mt-2 px-2 text-xs text-[var(--trk-warning)]">
          Multiple matches on this page — narrowed using row context; verify highlight on PDF.
        </p>
      ) : null}
      {viewportSize.width === 0 && !loading ? (
        <p className="p-4 text-sm text-[var(--trk-text-muted)]">No PDF page to display.</p>
      ) : null}
    </div>
  );
}
