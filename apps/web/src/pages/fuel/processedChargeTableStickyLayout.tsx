import { useCallback, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";

/**
 * Sticky failure cause (processed Fuel Home):
 * - `position: sticky` on thead/th is scoped to the nearest scroll ancestor.
 * - `.bvd-txn-rows.bvd-statement__table-wrap { overflow-x: auto }` (and/or
 *   `.fuel-recent-activity__scroll { overflow-x: auto }`) creates that ancestor.
 * - With no vertical overflow inside the wrapper, the header scrolls away with the page
 *   instead of sticking to `.trk-app-main`.
 * Fix: sticky host sits outside the horizontal scroller; sync scrollLeft + column widths from body table.
 */

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
  for (let i = 0; i < n; i += 1) {
    const w = bodyCells[i].getBoundingClientRect().width;
    const th = headerCells[i] as HTMLElement;
    th.style.width = `${w}px`;
    th.style.minWidth = `${w}px`;
    th.style.maxWidth = `${w}px`;
  }
  headerTable.style.width = `${bodyTable.getBoundingClientRect().width}px`;
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
    if (!bodyTable || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => syncWidths());
    ro.observe(bodyTable);
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
