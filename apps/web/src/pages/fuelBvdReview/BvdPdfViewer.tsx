import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { AnnotationMode, PixelsPerInch } from "pdfjs-dist";
import { EventBus, PDFPageView } from "pdfjs-dist/web/pdf_viewer.mjs";
import "pdfjs-dist/web/pdf_viewer.css";
import "./bvd-pdf-viewer.css";
import type { HighlightLookupContext } from "./bvdPdfHighlight";
import { mapPdfJsTextItems } from "./bvdPdfHighlight";
import { resolveDomHighlightRect, scrollContainerToHighlight } from "./bvdPdfDomHighlight";

export const BVD_PDF_ZOOM_DEFAULT = 125;
export const BVD_PDF_ZOOM_MIN = 50;
export const BVD_PDF_ZOOM_MAX = 250;
export const BVD_PDF_ZOOM_STEP = 10;

type Props = {
  document: PDFDocumentProxy | null;
  pageNumber: number;
  zoomPercent: number;
  highlightContext: HighlightLookupContext | null;
  loading?: boolean;
  error?: string | null;
};

type TextLayerRenderedEvent = {
  pageNumber: number;
  source: PDFPageView;
  error?: Error | null;
};

export default function BvdPdfViewer({
  document: pdfDocument,
  pageNumber,
  zoomPercent,
  highlightContext,
  loading,
  error,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const eventBusRef = useRef<EventBus | null>(null);
  const pageViewRef = useRef<PDFPageView | null>(null);
  const highlightLayerRef = useRef<HTMLDivElement | null>(null);
  const highlightContextRef = useRef(highlightContext);
  highlightContextRef.current = highlightContext;

  const renderGenerationRef = useRef(0);
  const highlightGenerationRef = useRef(0);

  const pageNumberRef = useRef(pageNumber);
  pageNumberRef.current = pageNumber;
  const zoomPercentRef = useRef(zoomPercent);
  zoomPercentRef.current = zoomPercent;
  const pdfDocumentRef = useRef(pdfDocument);
  pdfDocumentRef.current = pdfDocument;

  const [renderError, setRenderError] = useState<string | null>(null);
  const [ambiguousMessage, setAmbiguousMessage] = useState<string | null>(null);

  const clearHighlightDom = () => {
    if (highlightLayerRef.current) highlightLayerRef.current.innerHTML = "";
  };

  const clearHighlight = () => {
    setAmbiguousMessage(null);
    clearHighlightDom();
  };

  const bumpHighlightGeneration = () => {
    highlightGenerationRef.current += 1;
    return highlightGenerationRef.current;
  };

  const applyHighlightFromTextLayer = async (
    pageView: PDFPageView,
    token: { renderGen: number; highlightGen: number },
  ) => {
    if (token.renderGen !== renderGenerationRef.current) return;
    if (token.highlightGen !== highlightGenerationRef.current) return;
    if (pageView !== pageViewRef.current) return;
    if (pageView.id !== pageNumberRef.current) return;
    if (!pdfDocumentRef.current) return;

    const ctx = highlightContextRef.current;
    if (!ctx || !pageView.pdfPage) {
      clearHighlightDom();
      return;
    }
    if (ctx.page !== pageNumberRef.current) {
      clearHighlightDom();
      return;
    }

    clearHighlightDom();
    setAmbiguousMessage(null);

    const text = await pageView.pdfPage.getTextContent();
    if (token.renderGen !== renderGenerationRef.current) return;
    if (token.highlightGen !== highlightGenerationRef.current) return;
    if (pageView !== pageViewRef.current) return;

    const items = mapPdfJsTextItems(
      text.items.filter((i): i is { str: string; transform: number[]; width: number; height: number } => "str" in i),
    );
    const { rect, ambiguous } = resolveDomHighlightRect(pageView.div, items, ctx);

    if (token.renderGen !== renderGenerationRef.current) return;
    if (token.highlightGen !== highlightGenerationRef.current) return;
    if (pageView !== pageViewRef.current) return;
    if (highlightContextRef.current?.selectionKey !== ctx.selectionKey) return;
    if (ctx.page !== pageNumberRef.current) return;

    if (!rect || ambiguous) {
      setAmbiguousMessage("Source location ambiguous");
      return;
    }

    const layer = highlightLayerRef.current;
    if (!layer) return;

    const box = globalThis.document.createElement("div");
    box.className = "bvd-field-highlight";
    box.dataset.bvdHighlight = "1";
    box.style.left = `${rect.left}px`;
    box.style.top = `${rect.top}px`;
    box.style.width = `${rect.width}px`;
    box.style.height = `${rect.height}px`;
    layer.append(box);

    requestAnimationFrame(() => {
      if (token.highlightGen !== highlightGenerationRef.current) return;
      const scrollEl = scrollRef.current;
      if (scrollEl) scrollContainerToHighlight(scrollEl, pageView.div, rect);
    });
  };

  const scheduleHighlightAfterTextLayer = (pageView: PDFPageView) => {
    const highlightGen = highlightGenerationRef.current;
    const renderGen = renderGenerationRef.current;
    void applyHighlightFromTextLayer(pageView, { renderGen, highlightGen });
  };

  useEffect(() => {
    if (!eventBusRef.current) eventBusRef.current = new EventBus();
    return () => {
      pageViewRef.current?.destroy();
      pageViewRef.current = null;
    };
  }, []);

  useEffect(() => {
    clearHighlight();
    bumpHighlightGeneration();
  }, [pageNumber, zoomPercent]);

  useEffect(() => {
    bumpHighlightGeneration();
    const pageView = pageViewRef.current;
    if (pageView && pageView.id === pageNumber) {
      scheduleHighlightAfterTextLayer(pageView);
    }
  }, [highlightContext, pageNumber]);

  useEffect(() => {
    let cancelled = false;
    const eventBus = eventBusRef.current;
    let onTextLayerRendered: ((evt: TextLayerRenderedEvent) => void) | null = null;
    const renderGen = ++renderGenerationRef.current;
    bumpHighlightGeneration();
    clearHighlight();

    async function renderPage() {
      setRenderError(null);
      clearHighlight();
      if (!pdfDocument || !viewerRef.current || !eventBus) return;

      pageViewRef.current?.destroy();
      pageViewRef.current = null;
      viewerRef.current.innerHTML = "";
      highlightLayerRef.current = null;

      const scale = zoomPercent / 100;
      try {
        const pdfPage = await pdfDocument.getPage(pageNumber);
        if (cancelled || renderGen !== renderGenerationRef.current) return;

        const viewport = pdfPage.getViewport({ scale: scale * PixelsPerInch.PDF_TO_CSS_UNITS });
        const pageView = new PDFPageView({
          container: viewerRef.current,
          id: pageNumber,
          scale,
          defaultViewport: viewport,
          eventBus,
          annotationMode: AnnotationMode.DISABLE,
          textLayerMode: 1,
        });
        pageView.setPdfPage(pdfPage);
        pageViewRef.current = pageView;

        const pageDiv = pageView.div;
        pageDiv.style.position = "relative";
        const highlightLayer = globalThis.document.createElement("div");
        highlightLayer.className = "bvd-highlight-layer";
        highlightLayerRef.current = highlightLayer;
        pageDiv.append(highlightLayer);

        onTextLayerRendered = (evt: TextLayerRenderedEvent) => {
          if (evt.pageNumber !== pageNumber) return;
          if (evt.source !== pageViewRef.current) return;
          if (renderGen !== renderGenerationRef.current) return;
          if (evt.error) return;
          scheduleHighlightAfterTextLayer(evt.source);
        };
        eventBus.on("textlayerrendered", onTextLayerRendered);

        await pageView.draw();
      } catch (e: unknown) {
        if (!cancelled && renderGen === renderGenerationRef.current) {
          setRenderError(e instanceof Error ? e.message : "PDF render failed");
        }
      }
    }

    void renderPage();
    return () => {
      cancelled = true;
      if (onTextLayerRendered && eventBus) eventBus.off("textlayerrendered", onTextLayerRendered);
    };
  }, [pdfDocument, pageNumber, zoomPercent]);

  useEffect(() => {
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;
    const ro = new ResizeObserver(() => {
      const pageView = pageViewRef.current;
      if (!pageView) return;
      const highlightGen = highlightGenerationRef.current;
      const renderGen = renderGenerationRef.current;
      void applyHighlightFromTextLayer(pageView, { renderGen, highlightGen });
    });
    ro.observe(scrollEl);
    return () => ro.disconnect();
  }, []);

  if (error) {
    return <div className="p-4 text-sm text-[var(--trk-danger)]">{error}</div>;
  }
  if (loading) {
    return <div className="p-4 text-sm text-[var(--trk-text-muted)]">Loading PDF…</div>;
  }

  return (
    <div ref={scrollRef} className="bvd-pdf-scroll bg-[var(--trk-surface)] p-3">
      {renderError ? <p className="mb-2 text-sm text-[var(--trk-danger)]">{renderError}</p> : null}
      {ambiguousMessage ? (
        <p className="mb-2 text-xs text-[var(--trk-warning)]">{ambiguousMessage}</p>
      ) : null}
      <div ref={viewerRef} className="pdfViewer bvd-pdf-viewer" />
      {!pdfDocument && !loading ? (
        <p className="p-4 text-sm text-[var(--trk-text-muted)]">No PDF to display.</p>
      ) : null}
    </div>
  );
}
