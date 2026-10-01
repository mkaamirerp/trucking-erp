import { useCallback, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";

/**
 * Sticky failure cause (processed Fuel Home):
 * - `position: sticky` on thead/th is scoped to the nearest scroll ancestor.
 * - `.bvd-txn-rows.bvd-statement__table-wrap { overflow-x: auto }` (and/or
 *   `.fuel-recent-activity__scroll { overflow-x: auto }`) creates that ancestor.
 * - With no vertical overflow inside the wrapper, the header scrolls away with the page
 *   instead of sticking to `.trk-app-main`.
 * Fix: sticky host sits outside the horizontal scroller; sync scrollLeft + column widths from body table.
 *
 * Header overlap cause: copying only squeezed body cell widths onto a detached header row — header
 * labels need at least max(body, header content) per column.
 */

function measureCellContentWidth(cell: HTMLElement): number {
  return Math.ceil(Math.max(cell.getBoundingClientRect().width, cell.scrollWidth));
}

function measureHeaderCellNaturalWidth(th: HTMLElement): number {
  const prevWidth = th.style.width;
  const prevMin = th.style.minWidth;
  const prevMax = th.style.maxWidth;
  th.style.width = "";
  th.style.minWidth = "";
  th.style.maxWidth = "";
  const measured = Math.ceil(th.scrollWidth);
  th.style.width = prevWidth;
  th.style.minWidth = prevMin;
  th.style.maxWidth = prevMax;
  return measured;
}

/** Exported for unit tests — header minimum wins when wider than body. */
export function columnSyncWidthPx(bodyCell: HTMLElement, headerCell: HTMLElement): number {
  const bodyW = measureCellContentWidth(bodyCell);
  const headerW = Math.max(measureCellContentWidth(headerCell), measureHeaderCellNaturalWidth(headerCell));
  return Math.max(bodyW, headerW, 1);
}

function applySyncedColumnWidth(cell: HTMLElement, widthPx: number) {
  const w = `${widthPx}px`;
  cell.style.width = w;
  cell.style.minWidth = w;
  cell.style.maxWidth = w;
}

export function syncTableHeaderColumnWidths(
  bodyTable: HTMLTableElement | null,
  headerTable: HTMLTableElement | null,
) {
  if (!bodyTable || !headerTable) return;
  const bodyRow = bodyTable.querySelector("tbody tr:not(.bvd-txn-rows__detail-row)");
  const headerRow = headerTable.querySelector("thead tr");
  if (!bodyRow || !headerRow) return;

  const bodyCells = bodyRow.querySelectorAll(":scope > td");
  const headerCells = headerRow.querySelectorAll(":scope > th");
  const n = Math.min(bodyCells.length, headerCells.length);
  let total = 0;
  for (let i = 0; i < n; i += 1) {
    const widthPx = columnSyncWidthPx(bodyCells[i] as HTMLElement, headerCells[i] as HTMLElement);
    applySyncedColumnWidth(bodyCells[i] as HTMLElement, widthPx);
    applySyncedColumnWidth(headerCells[i] as HTMLElement, widthPx);
    total += widthPx;
  }
  const tableWidth = `${total}px`;
  bodyTable.style.width = tableWidth;
  headerTable.style.width = tableWidth;
}

export function useProcessedChargeTableSticky(bodyTableRef: RefObject<HTMLTableElement | null>) {
  const hScrollRef = useRef<HTMLDivElement | null>(null);
  const headerTableRef = useRef<HTMLTableElement | null>(null);
  const [scrollLeft, setScrollLeft] = useState(0);

  const syncWidths = useCallback(() => {
    syncTableHeaderColumnWidths(bodyTableRef.current, headerTableRef.current);
  }, [bodyTableRef]);

  const onHScroll = useCallback(() => {
    const el = hScrollRef.current;
    if (!el) return;
    setScrollLeft(el.scrollLeft);
  }, []);

  useLayoutEffect(() => {
    syncWidths();
    const bodyTable = bodyTableRef.current;
    const headerTable = headerTableRef.current;
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => syncWidths());
    if (bodyTable) ro.observe(bodyTable);
    if (headerTable) ro.observe(headerTable);
    return () => ro.disconnect();
  }, [bodyTableRef, syncWidths]);

  return { hScrollRef, headerTableRef, scrollLeft, onHScroll, syncWidths };
}

type StickyShellProps = {
  stickyTestId: string;
  headerTable: ReactNode;
  bodyTable: ReactNode;
  hScrollRef: RefObject<HTMLDivElement | null>;
  scrollLeft: number;
  onHScroll: () => void;
  outerTestId?: string;
  outerClassName?: string;
  outerDataAttrs?: Record<string, string>;
};

export function ProcessedChargeStickyShell({
  stickyTestId,
  headerTable,
  bodyTable,
  hScrollRef,
  scrollLeft,
  onHScroll,
  outerTestId,
  outerClassName,
  outerDataAttrs,
}: StickyShellProps) {
  return (
    <div
      className={`bvd-processed-charge-table ${outerClassName ?? ""}`.trim()}
      data-testid={outerTestId}
      {...(outerDataAttrs ?? {})}
    >
      <div className="bvd-processed-charge-table__sticky-host" data-testid={stickyTestId}>
        <div className="bvd-processed-charge-table__sticky-clip">
          <div
            className="bvd-processed-charge-table__sticky-track"
            style={{ transform: `translate3d(-${scrollLeft}px, 0, 0)` }}
            data-testid={`${stickyTestId}-track`}
          >
            {headerTable}
          </div>
        </div>
      </div>
      <div
        ref={hScrollRef}
        className="bvd-processed-charge-table__hscroll"
        onScroll={onHScroll}
        data-testid={`${stickyTestId}-hscroll`}
      >
        {bodyTable}
      </div>
    </div>
  );
}
