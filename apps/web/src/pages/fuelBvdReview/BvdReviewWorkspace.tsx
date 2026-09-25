import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PDFPageView } from "pdfjs-dist/web/pdf_viewer.mjs";
import type { FuelBvdRow } from "../../api";
import BvdPdfPagePane, { type TextLayerReadyPayload } from "./BvdPdfPagePane";
import {
  BVD_PDF_ZOOM_DEFAULT,
  BVD_PDF_ZOOM_MAX,
  BVD_PDF_ZOOM_MIN,
  BVD_PDF_ZOOM_STEP,
} from "./bvdPdfConstants";
import { getReviewFieldState } from "./bvdFieldCapture";
import {
  buildReviewLogicalRowsMerged,
  formatReviewLineNumber,
  gutterMetricsForLine,
  linesOnPage,
  reviewLineForSelection,
  reviewLineForUnmapped,
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
import { useSynchronizedScroll } from "./useSynchronizedScroll";
import {
  draftKey,
  extractedValue,
  type DraftMap,
  isFieldCorrected,
  reviewedValue,
} from "./bvdReviewValues";

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

function PageOverlay({
  pageView,
  children,
}: {
  pageView: PDFPageView;
  children: React.ReactNode;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    pageView.div.style.position = "relative";
    pageView.div.append(host);
    return () => {
      host.remove();
    };
  }, [pageView]);
  return (
    <div ref={hostRef} className="pointer-events-none absolute inset-0 z-[6]">
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
  const [syncScroll, setSyncScroll] = useState(true);
  const [selected, setSelected] = useState<BvdFieldRef | null>(null);
  const [selectedUnmappedId, setSelectedUnmappedId] = useState<string | null>(null);
  const [slots, setSlots] = useState<BvdFieldSlot[]>([]);
  const [unmappedOnPage, setUnmappedOnPage] = useState<BvdUnmappedSourceField[]>([]);
  const [allUnmapped, setAllUnmapped] = useState<BvdUnmappedSourceField[]>([]);
  const [possibleUnmapped, setPossibleUnmapped] = useState<BvdPossibleUnmappedContent[]>([]);
  const unmappedByPageRef = useRef<Map<number, BvdUnmappedSourceField[]>>(new Map());
  const possibleByPageRef = useRef<Map<number, BvdPossibleUnmappedContent[]>>(new Map());
  const [slotGeneration, setSlotGeneration] = useState(0);
  const [ambiguousMsg, setAmbiguousMsg] = useState<string | null>(null);
  const [leftPageView, setLeftPageView] = useState<PDFPageView | null>(null);
  const [rightPageView, setRightPageView] = useState<PDFPageView | null>(null);

  const leftScrollRef = useRef<HTMLDivElement>(null);
  const rightScrollRef = useRef<HTMLDivElement>(null);
  const slotBuildGenRef = useRef(0);

  const pageCount = useMemo(
    () => Math.max(1, rows.reduce((m, r) => Math.max(m, r.source_page ?? 1), 1)),
    [rows],
  );

  const fieldSequence = useMemo(() => orderedFieldRefsForRows(rows), [rows]);
  const logicalRows = useMemo(
    () => buildReviewLogicalRowsMerged(rows, allUnmapped, slots),
    [rows, allUnmapped, slots],
  );
  const logicalLinesOnPage = useMemo(
    () => linesOnPage(logicalRows, currentPage),
    [logicalRows, currentPage],
  );
  const rowsOnPage = useMemo(
    () => rows.filter((r) => (r.source_page ?? 1) === currentPage),
    [rows, currentPage],
  );

  useSynchronizedScroll(leftScrollRef, rightScrollRef, syncScroll);

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

  const onRightTextLayer = useCallback(
    (payload: TextLayerReadyPayload) => {
      if (payload.pageNumber !== currentPage) return;
      setRightPageView(payload.pageView);
    },
    [currentPage],
  );

  useEffect(() => {
    setSlots([]);
    setUnmappedOnPage([]);
    setLeftPageView(null);
    setRightPageView(null);
    setAmbiguousMsg(null);
    slotBuildGenRef.current += 1;
    setSelected((sel) => (sel && sel.page !== currentPage ? null : sel));
    setSelectedUnmappedId(null);
  }, [currentPage, zoomPercent, pdfDocument]);

  useEffect(() => {
    unmappedByPageRef.current.clear();
    possibleByPageRef.current.clear();
    setAllUnmapped([]);
    setPossibleUnmapped([]);
  }, [pdfDocument, rows, zoomPercent]);

  useEffect(() => {
    onReviewBlockersChange?.({
      unmappedCount: allUnmapped.length,
      possibleUnmappedCount: possibleUnmapped.length,
      unmapped: allUnmapped,
      possible: possibleUnmapped,
    });
  }, [allUnmapped, possibleUnmapped, onReviewBlockersChange]);

  const activeSlot = useMemo(() => slotForRef(slots, selected), [slots, selected]);
  const activeUnmapped = useMemo(
    () => unmappedOnPage.find((u) => u.id === selectedUnmappedId) ?? null,
    [unmappedOnPage, selectedUnmappedId],
  );

  useEffect(() => {
    if (activeUnmapped) {
      setAmbiguousMsg(null);
      const rect = {
        left: activeUnmapped.left,
        top: activeUnmapped.top,
        width: activeUnmapped.width,
        height: activeUnmapped.height,
      };
      requestAnimationFrame(() => {
        if (leftScrollRef.current && leftPageView) {
          scrollContainerToHighlight(leftScrollRef.current, leftPageView.div, rect);
        }
        if (rightScrollRef.current && rightPageView) {
          scrollContainerToHighlight(rightScrollRef.current, rightPageView.div, rect);
        }
      });
      return;
    }
    if (!activeSlot || activeSlot.ambiguous) {
      setAmbiguousMsg(activeSlot?.ambiguous ? "Source location ambiguous" : null);
      return;
    }
    setAmbiguousMsg(null);
    const rect = { left: activeSlot.left, top: activeSlot.top, width: activeSlot.width, height: activeSlot.height };
    requestAnimationFrame(() => {
      if (leftScrollRef.current && leftPageView) {
        scrollContainerToHighlight(leftScrollRef.current, leftPageView.div, rect);
      }
      if (rightScrollRef.current && rightPageView) {
        scrollContainerToHighlight(rightScrollRef.current, rightPageView.div, rect);
      }
    });
  }, [activeSlot, activeUnmapped, slotGeneration, leftPageView, rightPageView]);

  const rowById = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);

  const activeLineNumber = useMemo(() => {
    if (selectedUnmappedId) return reviewLineForUnmapped(logicalRows, selectedUnmappedId);
    if (!selected) return null;
    const row = rowById.get(selected.fuelBvdId);
    if (!row) return null;
    return reviewLineForSelection(logicalRows, selected.fuelBvdId, selected.fieldName, row.row_type);
  }, [selected, selectedUnmappedId, logicalRows, rowById]);

  const selectRef = (ref: BvdFieldRef) => {
    if (ref.page !== currentPage) setCurrentPage(ref.page);
    setSelectedUnmappedId(null);
    setSelected(ref);
  };

  const selectUnmapped = (field: BvdUnmappedSourceField) => {
    if (field.page !== currentPage) setCurrentPage(field.page);
    setSelected(null);
    setSelectedUnmappedId(field.id);
  };

  const onTabFromField = (backward: boolean) => {
    const seq = fieldSequence;
    if (!seq.length) return;
    const key = selected?.selectionKey;
    let idx = key ? seq.findIndex((f) => f.selectionKey === key) : -1;
    if (idx < 0) idx = backward ? seq.length : -1;
    const next = backward ? seq[idx - 1] : seq[idx + 1];
    if (!next) return;
    if (next.page !== currentPage) setCurrentPage(next.page);
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
            onClick={() => {
              setSelected(null);
              setCurrentPage((p) => p - 1);
            }}
            className="rounded border border-[var(--trk-border)] px-2 py-0.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span>Page {currentPage} of {pageCount}</span>
          <button
            type="button"
            disabled={currentPage >= pageCount}
            onClick={() => {
              setSelected(null);
              setCurrentPage((p) => p + 1);
            }}
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
          <label className="flex items-center gap-1 text-[var(--trk-text-muted)]">
            <input type="checkbox" checked={syncScroll} onChange={(e) => setSyncScroll(e.target.checked)} />
            Sync scroll
          </label>
        </div>
      </header>

      {ambiguousMsg ? <p className="px-3 py-1 text-xs text-[var(--trk-warning)]">{ambiguousMsg}</p> : null}
      {allUnmapped.length > 0 ? (
        <p className="px-3 py-1 text-xs text-[var(--trk-warning)]">
          {allUnmapped.length} unmapped source field{allUnmapped.length === 1 ? "" : "s"} on this import — Process is
          blocked until resolved or the BVD contract is extended.
        </p>
      ) : null}
      {possibleUnmapped.length > 0 && allUnmapped.length === 0 ? (
        <p className="px-3 py-1 text-xs text-[var(--trk-text-muted)]">
          Possible unmapped source content on {possibleUnmapped.length} line(s) — review PDF context (low confidence).
        </p>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-2">
        <div className="flex min-h-0 min-w-0 flex-col">
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
            <div className="relative min-h-0 min-w-0 flex-1">
              <BvdPdfPagePane
                pdfDocument={pdfDocument}
                pageNumber={currentPage}
                zoomPercent={zoomPercent}
                embedded
                onTextLayerReady={onLeftTextLayer}
              />
            {leftPageView ? (
              <PageOverlay pageView={leftPageView}>
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
                {unmappedOnPage.map((u) => {
                  const isSel = selectedUnmappedId === u.id;
                  return (
                    <button
                      key={`unmapped-hit-${u.id}`}
                      type="button"
                      title="Unmapped source field"
                      onClick={() => selectUnmapped(u)}
                      className={`absolute rounded border-2 bvd-unmapped-hit ${
                        isSel ? "ring-2 ring-[var(--trk-warning)]" : "opacity-90"
                      }`}
                      style={{ left: u.left, top: u.top, width: u.width, height: Math.max(u.height, 24) }}
                    />
                  );
                })}
              </PageOverlay>
            ) : null}
            </div>
          </div>
        </div>

        <div className="flex min-h-0 min-w-0 flex-col">
          <p className="shrink-0 border-b border-[var(--trk-border)] px-2 py-1 text-[10px] font-semibold uppercase text-[var(--trk-text-muted)]">
            Digital BVD review
          </p>
          <div ref={rightScrollRef} className="bvd-review-scroll-row bvd-pdf-scroll min-h-0 flex-1">
            <ReviewLineGutter
              lines={logicalLinesOnPage}
              slots={slotsForRows}
              unmappedOnPage={unmappedOnPage}
              activeLineNumber={activeLineNumber}
            />
            <div className="relative min-h-0 min-w-0 flex-1">
              <BvdPdfPagePane
                pdfDocument={pdfDocument}
                pageNumber={currentPage}
                zoomPercent={zoomPercent}
                embedded
                pageOpacity={0.22}
                onTextLayerReady={onRightTextLayer}
              />
            {rightPageView ? (
              <PageOverlay pageView={rightPageView}>
                {slotsForRows.map((slot) => {
                  const row = rowById.get(slot.fuelBvdId);
                  if (!row) return null;
                  const fieldState = getReviewFieldState(row, slot.fieldName, slot);
                  const captured = extractedValue(row, slot.fieldName);
                  const value = reviewedValue(row, slot.fieldName, drafts);
                  const corrected = isFieldCorrected(row, slot.fieldName, drafts);
                  const isSel = selected?.selectionKey === slot.selectionKey;
                  const showEditable = fieldState === "captured" || fieldState === "valid_blank";
                  return (
                    <div
                      key={`mirror-${slot.selectionKey}`}
                      className="absolute"
                      style={{ left: slot.left, top: slot.top, width: slot.width, height: slot.height }}
                    >
                      {showEditable ? (
                        <input
                          type="text"
                          disabled={readOnly}
                          value={value}
                          placeholder={fieldState === "valid_blank" ? "Blank" : undefined}
                          title={corrected ? `Original: ${captured}` : undefined}
                          onChange={(e) => onDraft(row.id, slot.fieldName, e.target.value)}
                          onFocus={() => selectRef(slot)}
                          className={`h-full w-full bg-[var(--trk-surface)]/95 px-0.5 text-xs text-[var(--trk-text)] outline-none placeholder:text-[var(--trk-text-muted)]/40 ${
                            isSel ? "ring-2 ring-[var(--trk-accent)]" : "border border-transparent hover:border-[var(--trk-border)]"
                          } ${corrected ? "text-[var(--trk-warning)]" : ""}`}
                        />
                      ) : (
                        <span
                          className="flex h-full w-full items-center bg-[var(--trk-surface)]/95 px-0.5 text-[10px] text-[var(--trk-danger)] ring-1 ring-[var(--trk-danger)]/50"
                          title="Not captured in TruckERP"
                        >
                          Not captured
                        </span>
                      )}
                    </div>
                  );
                })}
                {unmappedOnPage.map((u) => {
                  const isSel = selectedUnmappedId === u.id;
                  return (
                    <button
                      key={`unmapped-mirror-${u.id}`}
                      type="button"
                      onClick={() => selectUnmapped(u)}
                      className={`bvd-unmapped-mirror absolute text-left ${isSel ? "ring-2 ring-[var(--trk-warning)]" : ""}`}
                      style={{
                        left: u.left,
                        top: u.top,
                        width: Math.max(u.width, 120),
                        minHeight: Math.max(u.height, 36),
                      }}
                    >
                      <span className="block font-semibold text-[var(--trk-warning)]">Unmapped source field</span>
                      <span className="block text-[var(--trk-text-muted)]">Label: {u.label}</span>
                      {u.sourceValue ? (
                        <span className="block">Source: {u.sourceValue}</span>
                      ) : (
                        <span className="block text-[var(--trk-text-muted)]">Source: —</span>
                      )}
                    </button>
                  );
                })}
              </PageOverlay>
            ) : null}
            </div>
          </div>
        </div>
      </div>

      <footer className="shrink-0 border-t border-[var(--trk-border)] bg-[var(--trk-surface)] px-4 py-3">{footer}</footer>
    </div>
  );
}
