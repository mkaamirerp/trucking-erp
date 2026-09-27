import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PDFPageView } from "pdfjs-dist/web/pdf_viewer.mjs";
import type { FuelBvdRow } from "../../api";
import BvdPdfPagePane, { type TextLayerReadyPayload } from "./BvdPdfPagePane";
import BvdReviewFormPane from "./BvdReviewFormPane";
import {
  BVD_PDF_ZOOM_DEFAULT,
  BVD_PDF_ZOOM_MAX,
  BVD_PDF_ZOOM_MIN,
  BVD_PDF_ZOOM_STEP,
} from "./bvdPdfConstants";
import { resetScrollContainersToOrigin, type PageTransitionIntent } from "./bvdPageScroll";
import {
  buildReviewLogicalRowsMerged,
  formatReviewLineNumber,
  gutterMetricsForLine,
  reviewLineForSelection,
  visibleLinesOnPage,
  type BvdReviewLogicalRow,
} from "./bvdReviewLines";
import {
  discoverUnmappedSourceFields,
  type BvdPossibleUnmappedContent,
  type BvdUnmappedSourceField,
} from "./bvdUnmappedSource";
import {
  buildFieldSlotsForPage,
  orderedFieldRefsForRows,
  slotForRef,
  type BvdFieldRef,
  type BvdFieldSlot,
} from "./bvdFieldSlots";
import { mapPdfJsTextItems } from "./bvdPdfHighlight";
import { scrollContainerToHighlight } from "./bvdPdfDomHighlight";
import type { DraftMap } from "./bvdReviewValues";
import "./bvd-review-form.css";

function ReviewLineGutter({
  lines,
  slots,
  unmappedOnPage,
  activeLineNumber,
}: {
  lines: BvdReviewLogicalRow[];
  slots: BvdFieldSlot[];
  unmappedOnPage: BvdUnmappedSourceField[];
  activeLineNumber: number | null;
}) {
  const gutterHeight = useMemo(() => {
    const fromSlots = slots.length ? Math.max(...slots.map((s) => s.top + s.height)) : 0;
    const fromUnmapped = unmappedOnPage.length ? Math.max(...unmappedOnPage.map((u) => u.top + u.height)) : 0;
    return Math.max(400, fromSlots, fromUnmapped) + 24;
  }, [slots, unmappedOnPage]);

  return (
    <div className="bvd-line-gutter" style={{ minHeight: gutterHeight }}>
      {lines.map((line) => {
        const metrics = gutterMetricsForLine(slots, line, unmappedOnPage);
        if (!metrics) return null;
        const active = activeLineNumber === line.reviewLineNumber;
        return (
          <div
            key={`${line.fuelBvdId}-${line.headerField ?? line.unmappedId ?? line.rowType}-${line.reviewLineNumber}`}
            className={`bvd-line-gutter__n${active ? " bvd-line-gutter__n--active" : ""}`}
            style={{ top: metrics.top, height: metrics.height }}
          >
            {formatReviewLineNumber(line.reviewLineNumber)}
          </div>
        );
      })}
    </div>
  );
}

export type BvdReviewBlockers = {
  unmappedCount: number;
  possibleUnmappedCount: number;
  unmapped: BvdUnmappedSourceField[];
  possible: BvdPossibleUnmappedContent[];
};

function PageAlignedOverlay({
  containerRef,
  pageView,
  pageNumber,
  children,
}: {
  containerRef: React.RefObject<HTMLDivElement | null>;
  pageView: PDFPageView;
  pageNumber: number;
  children: React.ReactNode;
}) {
  const [box, setBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);

  useLayoutEffect(() => {
    if (pageView.id !== pageNumber) {
      setBox(null);
      return;
    }
    const pageDiv = pageView.div;
    const container = containerRef.current;
    if (!container) return;

    const sync = () => {
      if (pageView.id !== pageNumber) return;
      const cr = container.getBoundingClientRect();
      const pr = pageDiv.getBoundingClientRect();
      setBox({
        left: pr.left - cr.left + container.scrollLeft,
        top: pr.top - cr.top + container.scrollTop,
        width: pr.width,
        height: pr.height,
      });
    };

    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(pageDiv);
    container.addEventListener("scroll", sync, { passive: true });
    return () => {
      ro.disconnect();
      container.removeEventListener("scroll", sync);
    };
  }, [containerRef, pageView, pageNumber]);

  if (!box || pageView.id !== pageNumber) return null;

  return (
    <div
      className="pointer-events-none absolute z-[6]"
      style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
    >
      <div className="pointer-events-auto relative h-full w-full">{children}</div>
    </div>
  );
}

type Props = {
  pdfDocument: PDFDocumentProxy | null;
  rows: FuelBvdRow[];
  drafts: DraftMap;
  onDraft: (rowId: number, field: string, value: string) => void;
  readOnly: boolean;
  invoiceLabel: string;
  cardLabel: string;
  statusLabel: string;
  pdfLoading?: boolean;
  pdfError?: string | null;
  footer: React.ReactNode;
  onReviewBlockersChange?: (blockers: BvdReviewBlockers) => void;
};

export default function BvdReviewWorkspace({
  pdfDocument,
  rows,
  drafts,
  onDraft,
  readOnly,
  invoiceLabel,
  cardLabel,
  statusLabel,
  pdfLoading,
  pdfError,
  footer,
  onReviewBlockersChange,
}: Props) {
  const [currentPage, setCurrentPage] = useState(1);
  const [zoomPercent, setZoomPercent] = useState(BVD_PDF_ZOOM_DEFAULT);
  const [selected, setSelected] = useState<BvdFieldRef | null>(null);
  const [slots, setSlots] = useState<BvdFieldSlot[]>([]);
  const [unmappedOnPage, setUnmappedOnPage] = useState<BvdUnmappedSourceField[]>([]);
  const [allUnmapped, setAllUnmapped] = useState<BvdUnmappedSourceField[]>([]);
  const [possibleUnmapped, setPossibleUnmapped] = useState<BvdPossibleUnmappedContent[]>([]);
  const unmappedByPageRef = useRef<Map<number, BvdUnmappedSourceField[]>>(new Map());
  const possibleByPageRef = useRef<Map<number, BvdPossibleUnmappedContent[]>>(new Map());
  const [slotGeneration, setSlotGeneration] = useState(0);
  const [ambiguousMsg, setAmbiguousMsg] = useState<string | null>(null);
  const [leftPageView, setLeftPageView] = useState<PDFPageView | null>(null);

  const leftScrollRef = useRef<HTMLDivElement>(null);
  const leftPaneRef = useRef<HTMLDivElement>(null);
  const pageTransitionIntentRef = useRef<PageTransitionIntent>(null);
  const slotBuildGenRef = useRef(0);

  const pageCount = useMemo(() => {
    if (pdfDocument?.numPages && pdfDocument.numPages > 0) return pdfDocument.numPages;
    return Math.max(1, rows.reduce((m, r) => Math.max(m, r.source_page ?? 1), 1));
  }, [pdfDocument, rows]);

  const fieldSequence = useMemo(() => orderedFieldRefsForRows(rows), [rows]);
  const logicalRows = useMemo(
    () => buildReviewLogicalRowsMerged(rows, allUnmapped, slots),
    [rows, allUnmapped, slots],
  );
  const logicalLinesOnPage = useMemo(
    () => visibleLinesOnPage(logicalRows, currentPage, slots, unmappedOnPage),
    [logicalRows, currentPage, slots, unmappedOnPage],
  );
  const rowsOnPage = useMemo(
    () => rows.filter((r) => (r.source_page ?? 1) === currentPage),
    [rows, currentPage],
  );

  const rebuildSlots = useCallback(
    async (pageView: PDFPageView, page: number) => {
      if (!pageView.pdfPage) return;
      const buildGen = ++slotBuildGenRef.current;
      const text = await pageView.pdfPage.getTextContent();
      if (buildGen !== slotBuildGenRef.current) return;
      const items = mapPdfJsTextItems(
        text.items.filter((i): i is { str: string; transform: number[]; width: number; height: number } => "str" in i),
      );
      const pageRows = rows.filter((r) => (r.source_page ?? 1) === page);
      const built = buildFieldSlotsForPage(pageView.div, items, pageRows);
      const discovery = discoverUnmappedSourceFields(pageView.div, items, page, built);
      if (buildGen !== slotBuildGenRef.current) return;
      unmappedByPageRef.current.set(page, discovery.unmapped);
      possibleByPageRef.current.set(page, discovery.possible);
      const mergedUnmapped: BvdUnmappedSourceField[] = [];
      const mergedPossible: BvdPossibleUnmappedContent[] = [];
      for (const list of unmappedByPageRef.current.values()) mergedUnmapped.push(...list);
      for (const list of possibleByPageRef.current.values()) mergedPossible.push(...list);
      setAllUnmapped(mergedUnmapped);
      setPossibleUnmapped(mergedPossible);
      setUnmappedOnPage(discovery.unmapped);
      setSlots(built);
      setSlotGeneration(buildGen);
    },
    [rows],
  );

  const onLeftTextLayer = useCallback(
    (payload: TextLayerReadyPayload) => {
      if (payload.pageNumber !== currentPage) return;
      setLeftPageView(payload.pageView);
      setAmbiguousMsg(null);
      void rebuildSlots(payload.pageView, payload.pageNumber);
    },
    [currentPage, rebuildSlots],
  );

  useEffect(() => {
    setSlots([]);
    setUnmappedOnPage([]);
    setLeftPageView(null);
    setAmbiguousMsg(null);
    slotBuildGenRef.current += 1;
  }, [currentPage, zoomPercent, pdfDocument]);

  useEffect(() => {
    unmappedByPageRef.current.clear();
    possibleByPageRef.current.clear();
    setAllUnmapped([]);
    setPossibleUnmapped([]);
  }, [pdfDocument, rows]);

  useEffect(() => {
    onReviewBlockersChange?.({
      unmappedCount: allUnmapped.length,
      possibleUnmappedCount: possibleUnmapped.length,
      unmapped: allUnmapped,
      possible: possibleUnmapped,
    });
  }, [allUnmapped, possibleUnmapped, onReviewBlockersChange]);

  const activeSlot = useMemo(() => slotForRef(slots, selected), [slots, selected]);
  const leftPaneReady = leftPageView?.id === currentPage;

  useEffect(() => {
    if (!leftPaneReady) return;
    const intent = pageTransitionIntentRef.current;
    if (intent === "manual") {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          resetScrollContainersToOrigin(leftScrollRef.current);
          pageTransitionIntentRef.current = null;
        });
      });
      return;
    }
    if (intent !== "field") return;
    if (!activeSlot || activeSlot.ambiguous) return;
    const rect = {
      left: activeSlot.left,
      top: activeSlot.top,
      width: activeSlot.width,
      height: activeSlot.height,
    };
    requestAnimationFrame(() => {
      if (leftScrollRef.current && leftPageView) {
        scrollContainerToHighlight(leftScrollRef.current, leftPageView.div, rect);
      }
      pageTransitionIntentRef.current = null;
    });
  }, [leftPaneReady, currentPage, slotGeneration, leftPageView, activeSlot]);

  useEffect(() => {
    if (pageTransitionIntentRef.current) return;
    if (!leftPaneReady) return;
    if (!activeSlot || activeSlot.ambiguous) {
      setAmbiguousMsg(activeSlot?.ambiguous ? "Source location ambiguous" : null);
      return;
    }
    if (activeSlot.page !== currentPage) return;
    setAmbiguousMsg(null);
    const rect = { left: activeSlot.left, top: activeSlot.top, width: activeSlot.width, height: activeSlot.height };
    requestAnimationFrame(() => {
      if (leftScrollRef.current && leftPageView) {
        scrollContainerToHighlight(leftScrollRef.current, leftPageView.div, rect);
      }
    });
  }, [activeSlot, slotGeneration, leftPageView, leftPaneReady, currentPage]);

  const rowById = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);

  const activeLineNumber = useMemo(() => {
    if (!selected) return null;
    const row = rowById.get(selected.fuelBvdId);
    if (!row) return null;
    return reviewLineForSelection(logicalRows, selected.fuelBvdId, selected.fieldName, row.row_type);
  }, [selected, logicalRows, rowById]);

  const goToPageForField = (page: number) => {
    if (page === currentPage) return;
    pageTransitionIntentRef.current = "field";
    setLeftPageView(null);
    setCurrentPage(page);
  };

  const goToPageManual = (page: number) => {
    pageTransitionIntentRef.current = "manual";
    setSelected(null);
    setLeftPageView(null);
    setCurrentPage(page);
  };

  const selectRef = (ref: BvdFieldRef) => {
    if (ref.page !== currentPage) goToPageForField(ref.page);
    setSelected(ref);
  };

  const onTabFromField = (backward: boolean) => {
    const seq = fieldSequence;
    if (!seq.length) return;
    const key = selected?.selectionKey;
    let idx = key ? seq.findIndex((f) => f.selectionKey === key) : -1;
    if (idx < 0) idx = backward ? seq.length : -1;
    const next = backward ? seq[idx - 1] : seq[idx + 1];
    if (!next) return;
    if (next.page !== currentPage) goToPageForField(next.page);
    setSelected(next);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Tab") {
      e.preventDefault();
      onTabFromField(e.shiftKey);
    }
  };

  const slotsForRows = slots.filter((s) => rowsOnPage.some((r) => r.id === s.fuelBvdId));

  if (pdfError) return <div className="p-4 text-sm text-[var(--trk-danger)]">{pdfError}</div>;
  if (pdfLoading) return <div className="p-4 text-sm text-[var(--trk-text-muted)]">Loading PDF…</div>;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col overflow-hidden bg-[var(--trk-bg)]" onKeyDown={handleKeyDown}>
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-[var(--trk-border)] px-3 py-2 text-xs">
        <span className="font-medium text-[var(--trk-text)]">{invoiceLabel}</span>
        <span className="text-[var(--trk-text-muted)]">{cardLabel}</span>
        <span className="text-[var(--trk-text-muted)]">Status: {statusLabel}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={currentPage <= 1}
            onClick={() => goToPageManual(currentPage - 1)}
            className="rounded border border-[var(--trk-border)] px-2 py-0.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span>Page {currentPage} of {pageCount}</span>
          <button
            type="button"
            disabled={currentPage >= pageCount}
            onClick={() => goToPageManual(currentPage + 1)}
            className="rounded border border-[var(--trk-border)] px-2 py-0.5 disabled:opacity-40"
          >
            Next
          </button>
          <button
            type="button"
            onClick={() => setZoomPercent((z) => Math.max(BVD_PDF_ZOOM_MIN, z - BVD_PDF_ZOOM_STEP))}
            className="rounded border border-[var(--trk-border)] px-1.5"
          >
            −
          </button>
          <span>{zoomPercent}%</span>
          <button
            type="button"
            onClick={() => setZoomPercent((z) => Math.min(BVD_PDF_ZOOM_MAX, z + BVD_PDF_ZOOM_STEP))}
            className="rounded border border-[var(--trk-border)] px-1.5"
          >
            +
          </button>
        </div>
      </header>

      {ambiguousMsg ? <p className="px-3 py-1 text-xs text-[var(--trk-warning)]">{ambiguousMsg}</p> : null}
      {allUnmapped.length > 0 ? (
        <p className="px-3 py-1 text-xs text-[var(--trk-warning)]">
          ⚠ {allUnmapped.length} unmapped source field{allUnmapped.length === 1 ? "" : "s"} — Process blocked until
          resolved.
        </p>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-2">
        <div className="flex min-h-0 min-w-0 flex-col border-r border-[var(--trk-border)]">
          <p className="shrink-0 border-b border-[var(--trk-border)] px-2 py-1 text-[10px] font-semibold uppercase text-[var(--trk-text-muted)]">
            Original BVD PDF
          </p>
          <div ref={leftScrollRef} className="bvd-review-scroll-row bvd-pdf-scroll min-h-0 flex-1">
            <ReviewLineGutter
              lines={logicalLinesOnPage}
              slots={slotsForRows}
              unmappedOnPage={unmappedOnPage}
              activeLineNumber={activeLineNumber}
            />
            <div ref={leftPaneRef} className="relative min-h-0 min-w-0 flex-1">
              <BvdPdfPagePane
                pdfDocument={pdfDocument}
                pageNumber={currentPage}
                zoomPercent={zoomPercent}
                embedded
                onTextLayerReady={onLeftTextLayer}
              />
              {leftPageView && leftPageView.id === currentPage ? (
                <PageAlignedOverlay containerRef={leftPaneRef} pageView={leftPageView} pageNumber={currentPage}>
                  {slotsForRows.map((slot) => {
                    const isSel = selected?.selectionKey === slot.selectionKey;
                    return (
                      <button
                        key={`hit-${slot.selectionKey}`}
                        type="button"
                        onClick={() => selectRef(slot)}
                        className={`absolute rounded border-2 ${
                          isSel
                            ? "border-[var(--trk-warning)] bg-[var(--trk-warning)]/30"
                            : "border-transparent hover:border-[var(--trk-warning)]/40"
                        }`}
                        style={{ left: slot.left, top: slot.top, width: slot.width, height: slot.height }}
                      />
                    );
                  })}
                </PageAlignedOverlay>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex min-h-0 min-w-0 flex-col bg-[var(--trk-surface)]">
          <p className="shrink-0 border-b border-[var(--trk-border)] px-2 py-1 text-[10px] font-semibold uppercase text-[var(--trk-warning)]">
            TruckERP review
          </p>
          <BvdReviewFormPane
            rows={rows}
            logicalRows={logicalRows}
            currentPage={currentPage}
            drafts={drafts}
            readOnly={readOnly}
            selected={selected}
            activeLineNumber={activeLineNumber}
            onSelect={selectRef}
            onDraft={onDraft}
            slots={slots}
          />
        </div>
      </div>

      <footer className="shrink-0 border-t border-[var(--trk-border)] bg-[var(--trk-surface)] px-4 py-3">{footer}</footer>
    </div>
  );
}
