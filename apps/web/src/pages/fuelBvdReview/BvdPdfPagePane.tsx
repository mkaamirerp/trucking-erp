import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { AnnotationMode, PixelsPerInch } from "pdfjs-dist";
import { EventBus, PDFPageView } from "pdfjs-dist/web/pdf_viewer.mjs";
import "pdfjs-dist/web/pdf_viewer.css";
import "./bvd-pdf-viewer.css";

export type TextLayerReadyPayload = {
  pageView: PDFPageView;
  pageNumber: number;
  renderGeneration: number;
};

type Props = {
  pdfDocument: PDFDocumentProxy | null;
  pageNumber: number;
  zoomPercent: number;
  scrollRef?: React.RefObject<HTMLDivElement | null>;
  pageOpacity?: number;
  pointerEvents?: "none" | "auto";
  onTextLayerReady?: (payload: TextLayerReadyPayload) => void;
  /** When true, parent owns scroll container (line gutter + sync scroll). */
  embedded?: boolean;
};

export default function BvdPdfPagePane({
  pdfDocument,
  pageNumber,
  zoomPercent,
  scrollRef: externalScrollRef,
  pageOpacity = 1,
  pointerEvents = "auto",
  onTextLayerReady,
  embedded = false,
}: Props) {
  const internalScrollRef = useRef<HTMLDivElement>(null);
  const scrollRef = externalScrollRef ?? internalScrollRef;
  const viewerRef = useRef<HTMLDivElement>(null);
  const eventBusRef = useRef<EventBus | null>(null);
  const pageViewRef = useRef<PDFPageView | null>(null);
  const renderGenerationRef = useRef(0);
  const onReadyRef = useRef(onTextLayerReady);
  onReadyRef.current = onTextLayerReady;
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    if (!eventBusRef.current) eventBusRef.current = new EventBus();
    return () => {
      pageViewRef.current?.destroy();
      pageViewRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const eventBus = eventBusRef.current;
    let onTextLayerRendered: ((evt: { pageNumber: number; source: PDFPageView; error?: Error | null }) => void) | null =
      null;
    const renderGen = ++renderGenerationRef.current;

    async function renderPage() {
      setRenderError(null);
      if (!pdfDocument || !viewerRef.current || !eventBus) return;

      pageViewRef.current?.destroy();
      pageViewRef.current = null;
      viewerRef.current.innerHTML = "";

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
        pageView.div.style.position = "relative";
        pageView.div.style.opacity = String(pageOpacity);

        onTextLayerRendered = (evt) => {
          if (evt.pageNumber !== pageNumber) return;
          if (evt.source !== pageViewRef.current) return;
          if (renderGen !== renderGenerationRef.current) return;
          if (evt.error) return;
          onReadyRef.current?.({ pageView: evt.source, pageNumber, renderGeneration: renderGen });
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
  }, [pdfDocument, pageNumber, zoomPercent, pageOpacity]);

  const viewer = (
    <>
      {renderError ? <p className="mb-2 text-sm text-[var(--trk-danger)]">{renderError}</p> : null}
      <div ref={viewerRef} className="pdfViewer bvd-pdf-viewer" />
    </>
  );

  if (embedded) {
    return <div style={{ pointerEvents }}>{viewer}</div>;
  }

  return (
    <div ref={scrollRef} className="bvd-pdf-scroll" style={{ pointerEvents }}>
      {viewer}
    </div>
  );
}
