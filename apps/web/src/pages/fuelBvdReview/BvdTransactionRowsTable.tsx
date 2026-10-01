import { Fragment, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ProcessedChargeStickyShell,
  useProcessedChargeTableSticky,
} from "../fuel/processedChargeTableStickyLayout";
import type { FuelBvdRow } from "../../api";
import { displayCell, operationalCell } from "./bvdParsedDisplay";
import { bvdProductDisplayLabel } from "./bvdProductDisplay";
import {
  activeBvdTxnTaxColumns,
  bvdTxnDiscountDisplay,
  bvdTxnTaxDisplay,
  type BvdTxnActiveTaxColumn,
} from "./fuelBvdTxnMoneyColumns";
import {
  type FuelBvdTxnSortColumn,
  type FuelBvdTxnSortState,
  sortFuelBvdTransactions,
} from "./fuelBvdTxnTableSort";
import {
  formatBvdTransactionDateTime,
  formatBvdTxnLocationShort,
  formatBvdTxnSiteDetail,
} from "./bvdTransactionRowPresentation";

type Props = {
  transactions: FuelBvdRow[];
  /** From statement header — shown in expanded panel only. */
  cardNumber: string;
  /** Processed workspace: sticky header outside horizontal scroller (Fuel Home expand). */
  processedStickyHeader?: boolean;
};

type ColumnDef = {
  key: FuelBvdTxnSortColumn;
  label: string;
  className?: string;
};

const BASE_SORTABLE_COLUMNS: ColumnDef[] = [
  { key: "date", label: "Date / Time", className: "bvd-txn-rows__col-compact" },
  { key: "unit", label: "Unit", className: "bvd-txn-rows__col-compact" },
  { key: "driver", label: "Source driver", className: "bvd-txn-rows__col-flex bvd-txn-rows__col-driver" },
  { key: "location", label: "Location", className: "bvd-txn-rows__col-flex" },
  { key: "product", label: "Product", className: "bvd-txn-rows__col-compact" },
  { key: "qty", label: "Qty", className: "bvd-txn-rows__col-compact bvd-txn-rows__col-numeric" },
];

const RETAIL_COLUMN: ColumnDef = {
  key: "retail",
  label: "Retail price",
  className: "bvd-txn-rows__col-compact bvd-txn-rows__col-numeric bvd-txn-rows__col-price",
};

const BILLED_COLUMN: ColumnDef = {
  key: "billed",
  label: "Billed price",
  className: "bvd-txn-rows__col-compact bvd-txn-rows__col-numeric bvd-txn-rows__col-price",
};

const DISCOUNT_COLUMN: ColumnDef = {
  key: "discount",
  label: "Discount",
  className: "bvd-txn-rows__col-compact bvd-txn-rows__col-numeric",
};

const TAIL_SORTABLE_COLUMNS: ColumnDef[] = [
  { key: "final", label: "Final amount", className: "bvd-txn-rows__col-compact bvd-txn-rows__col-amount" },
  { key: "currency", label: "Currency", className: "bvd-txn-rows__col-compact" },
];

function taxColumnDef(tax: BvdTxnActiveTaxColumn): ColumnDef {
  return {
    key: tax.field,
    label: tax.label,
    className: "bvd-txn-rows__col-compact bvd-txn-rows__col-numeric",
  };
}

function buildSortableColumns(activeTaxes: BvdTxnActiveTaxColumn[]): ColumnDef[] {
  return [
    ...BASE_SORTABLE_COLUMNS,
    RETAIL_COLUMN,
    BILLED_COLUMN,
    DISCOUNT_COLUMN,
    ...activeTaxes.map(taxColumnDef),
    ...TAIL_SORTABLE_COLUMNS,
  ];
}

function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <span className="bvd-txn-rows__chevron" aria-hidden="true">
      {expanded ? "▾" : "▸"}
    </span>
  );
}

function DetailField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="bvd-txn-rows__detail-cell">
      <span className="bvd-txn-rows__detail-label">{label}</span>
      <span className="bvd-txn-rows__detail-value">{children}</span>
    </div>
  );
}

function SortableHeader({
  column,
  label,
  className,
  sort,
  onSort,
}: {
  column: FuelBvdTxnSortColumn;
  label: string;
  className?: string;
  sort: FuelBvdTxnSortState | null;
  onSort: (column: FuelBvdTxnSortColumn) => void;
}) {
  const active = sort?.column === column;
  const ariaSort = active ? (sort.direction === "asc" ? "ascending" : "descending") : "none";
  const indicator = active ? (sort.direction === "asc" ? " ↑" : " ↓") : "";

  return (
    <th className={`bvd-txn-rows__header-cell ${className ?? ""}`} scope="col">
      <button
        type="button"
        className="bvd-txn-rows__sort-btn"
        data-testid={`bvd-txn-sort-${column}`}
        aria-sort={ariaSort}
        onClick={(e) => {
          e.stopPropagation();
          onSort(column);
        }}
      >
        <span className="bvd-txn-rows__sort-label">{label}</span>
        {active ? (
          <span className="bvd-txn-rows__sort-indicator" aria-hidden="true">{indicator}</span>
        ) : (
          <span className="bvd-txn-rows__sort-hint" aria-hidden="true">↕</span>
        )}
      </button>
    </th>
  );
}

export default function BvdTransactionRowsTable({
  transactions,
  cardNumber,
  processedStickyHeader = false,
}: Props) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [sort, setSort] = useState<FuelBvdTxnSortState | null>(null);
  const bodyTableRef = useRef<HTMLTableElement | null>(null);
  const sticky = useProcessedChargeTableSticky(bodyTableRef);

  const activeTaxes = useMemo(() => activeBvdTxnTaxColumns(transactions), [transactions]);
  const sortableColumns = useMemo(() => buildSortableColumns(activeTaxes), [activeTaxes]);
  const columnCount = 1 + sortableColumns.length;

  const displayTransactions = useMemo(() => {
    if (!sort) return transactions;
    return sortFuelBvdTransactions(transactions, sort);
  }, [transactions, sort]);

  const toggle = (id: number) => {
    setExpandedId((cur) => (cur === id ? null : id));
  };

  const handleSort = (column: FuelBvdTxnSortColumn) => {
    setSort((prev) => {
      if (prev?.column === column) {
        return { column, direction: prev.direction === "asc" ? "desc" : "asc" };
      }
      return { column, direction: "asc" };
    });
  };

  useLayoutEffect(() => {
    if (processedStickyHeader) sticky.syncWidths();
  }, [processedStickyHeader, displayTransactions, expandedId, sort, sticky]);

  const tableClass =
    "bvd-statement__table bvd-statement__table--txn bvd-statement__table--purchases bvd-txn-rows__table";

  const headerRow = (
    <thead className="bvd-txn-rows__thead">
      <tr className="bvd-txn-rows__header-row">
        <th className="bvd-txn-rows__col-chevron bvd-txn-rows__header-cell" aria-hidden="true" scope="col" />
        {sortableColumns.map((col) => (
          <SortableHeader
            key={col.key}
            column={col.key}
            label={col.label}
            className={col.className}
            sort={sort}
            onSort={handleSort}
          />
        ))}
      </tr>
    </thead>
  );

  const bodyRows = (
        <tbody>
          {displayTransactions.map((row) => {
            const expanded = expandedId === row.id;
            const site = formatBvdTxnSiteDetail(row);
            const finalAmt = operationalCell(row, "final_amt");
            const cur = operationalCell(row, "cur");
            const retail = displayCell(row, "retail");
            const billed = displayCell(row, "billed");

            return (
              <Fragment key={row.id}>
                <tr
                  className={`bvd-purchase-row bvd-txn-rows__main${expanded ? " bvd-txn-rows__main--expanded" : ""}`}
                  data-testid={`bvd-txn-row-${row.id}`}
                  data-expanded={expanded ? "true" : "false"}
                  onClick={() => toggle(row.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      toggle(row.id);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-expanded={expanded}
                >
                  <td className="bvd-txn-rows__chevron-cell">
                    <Chevron expanded={expanded} />
                  </td>
                  <td className="bvd-txn-rows__col-compact" data-testid="bvd-txn-col-date">
                    {formatBvdTransactionDateTime(operationalCell(row, "transaction_date"))}
                  </td>
                  <td className="bvd-txn-rows__col-compact" data-testid="bvd-txn-col-unit">
                    {operationalCell(row, "unit_number") || "—"}
                  </td>
                  <td
                    className="bvd-txn-rows__col-flex bvd-txn-rows__col-driver"
                    data-testid="bvd-txn-col-driver"
                  >
                    {operationalCell(row, "driver_name") || "—"}
                  </td>
                  <td className="bvd-txn-rows__col-flex" data-testid="bvd-txn-col-location">
                    {formatBvdTxnLocationShort(row)}
                  </td>
                  <td className="bvd-txn-rows__col-compact" data-testid="bvd-txn-col-product">
                    {bvdProductDisplayLabel(operationalCell(row, "prod"))}
                  </td>
                  <td
                    className="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric"
                    data-testid="bvd-txn-col-qty"
                  >
                    {operationalCell(row, "qty") || "—"}
                  </td>
                  <td
                    className="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric bvd-txn-rows__col-price"
                    data-testid="bvd-txn-col-retail"
                  >
                    {retail || "—"}
                  </td>
                  <td
                    className="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric bvd-txn-rows__col-price"
                    data-testid="bvd-txn-col-billed"
                  >
                    {billed || "—"}
                  </td>
                  <td
                    className="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric"
                    data-testid="bvd-txn-col-discount"
                  >
                    {bvdTxnDiscountDisplay(row)}
                  </td>
                  {activeTaxes.map((tax) => (
                    <td
                      key={tax.field}
                      className="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric"
                      data-testid={`bvd-txn-col-${tax.field}`}
                    >
                      {bvdTxnTaxDisplay(row, tax.field)}
                    </td>
                  ))}
                  <td
                    className="bvd-txn-rows__col-compact bvd-txn-rows__col-amount"
                    data-testid="bvd-txn-col-final"
                  >
                    {finalAmt || "—"}
                  </td>
                  <td className="bvd-txn-rows__col-compact" data-testid="bvd-txn-col-cur">
                    {cur || "—"}
                  </td>
                </tr>
                {expanded ? (
                  <tr key={`${row.id}-detail`} className="bvd-txn-rows__detail-row">
                    <td colSpan={columnCount}>
                      <div
                        className="bvd-txn-rows__detail-panel"
                        data-testid={`bvd-txn-detail-${row.id}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="bvd-txn-rows__detail-grid">
                          <DetailField label="Provider">BVD</DetailField>
                          <DetailField label="Card #">{cardNumber || "—"}</DetailField>
                          <DetailField label="Auth / reference">
                            {displayCell(row, "auth_code") || "—"}
                          </DetailField>
                          <DetailField label="Site">
                            <span className="bvd-txn-rows__site-block">
                              <span>{site.primaryLine}</span>
                              {site.secondaryLine ? <span>{site.secondaryLine}</span> : null}
                              {site.siteNumberLine ? (
                                <span className="bvd-txn-rows__site-num">{site.siteNumberLine}</span>
                              ) : null}
                            </span>
                          </DetailField>
                          <DetailField label="Pre-tax amount">
                            {operationalCell(row, "pre_tax_amt") || "—"}
                          </DetailField>
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
  );

  if (processedStickyHeader) {
    return (
      <ProcessedChargeStickyShell
        stickyTestId="bvd-txn-sticky-header"
        outerTestId="bvd-txn-rows-table"
        outerClassName="bvd-txn-rows"
        outerDataAttrs={{
          "data-active-tax-columns": activeTaxes.map((t) => t.field).join(","),
        }}
        hScrollRef={sticky.hScrollRef}
        scrollLeft={sticky.scrollLeft}
        onHScroll={sticky.onHScroll}
        headerTable={
          <table ref={sticky.headerTableRef} className={`${tableClass} bvd-processed-charge-table__header-table`}>
            {headerRow}
          </table>
        }
        bodyTable={
          <table ref={bodyTableRef} className={tableClass}>
            {bodyRows}
          </table>
        }
      />
    );
  }

  return (
    <div
      className="bvd-statement__table-wrap bvd-txn-rows"
      data-testid="bvd-txn-rows-table"
      data-active-tax-columns={activeTaxes.map((t) => t.field).join(",")}
    >
      <table className={tableClass}>
        {headerRow}
        {bodyRows}
      </table>
    </div>
  );
}
