import { Fragment, useCallback, useState, type ReactNode } from "react";
import { fuelReviewBatchDocumentUrl, type FuelProcessedSummary } from "../../api";
import { OPS } from "../../routes";
import { fuelActivityRowFromProcessed, type FuelActivityRow } from "./fuelActivityRow";
import {
  formatFuelActivityAccountCard,
  formatFuelActivityDueDate,
  formatFuelActivityPeriod,
  fuelActivityPaymentLabel,
} from "./fuelActivityInvoiceDisplay";
import {
  formatFuelCurrencyFinancialDiscount,
  formatFuelCurrencyFinancialTotal,
  resolveFuelCurrencyFinancialSummaries,
  type FuelCurrencyFinancialLine,
} from "./fuelActivityCurrencyFinancial";
import ProcessedFuelStatementShell from "./ProcessedFuelStatementShell";
import "../fuelBvdReview/bvd-parsed-statement.css";
import "./fuel-home.css";

type Props = {
  activity: FuelProcessedSummary[];
  loading: boolean;
  heading?: string;
  showViewAllLink?: boolean;
  onViewAllClick?: () => void;
  emptyMessage?: string;
  onOpenProcessed?: (batchId: number, providerCode: string, sourceImportRef: string | null) => void;
  highlightBatchId?: number | null;
};

function providerTableLabel(code: string): string {
  if (code === "NATIONWIDE") return "Nationwide";
  if (code === "MANUAL_ENTRY") return "MANUAL_ENTRY";
  return code;
}

function InvoiceTotalStack({ lines }: { lines: FuelCurrencyFinancialLine[] }) {
  if (lines.length === 0) {
    return <span className="text-[var(--trk-text-muted)]">—</span>;
  }
  return (
    <div className="fuel-activity-money-stack" data-testid="fuel-activity-invoice-total-stack">
      {lines.map((line) => (
        <div
          key={line.currency}
          className="fuel-activity-money-stack__line tabular-nums font-medium"
          data-testid={`fuel-activity-invoice-total-line-${line.currency}`}
        >
          {formatFuelCurrencyFinancialTotal(line)}
        </div>
      ))}
    </div>
  );
}

type InvoiceBandProps = {
  summary: FuelProcessedSummary;
  row: FuelActivityRow;
  isExpanded: boolean;
  highlighted: boolean;
  onToggle: () => void;
  onOpenProcessed?: (batchId: number, providerCode: string, sourceImportRef: string | null) => void;
};

function FuelActivityInvoiceBand({
  summary,
  row,
  isExpanded,
  highlighted,
  onToggle,
  onOpenProcessed,
}: InvoiceBandProps) {
  const lines = resolveFuelCurrencyFinancialSummaries(summary);
  const bandLines: FuelCurrencyFinancialLine[] =
    lines.length > 0
      ? lines
      : [
          {
            currency: "—",
            total_amount: "",
            discount_amount: null,
          },
        ];
  const bandSize = bandLines.length;
  const rowClassBase = `fuel-activity-invoice-band${
    isExpanded ? " fuel-activity-invoice-band--expanded" : ""
  }${highlighted ? " fuel-activity-invoice-band--highlight" : ""}`;

  const identityCells = (lineIndex: number): ReactNode => {
    if (lineIndex !== 0) return null;
    return (
      <>
        <td
          rowSpan={bandSize}
          className="fuel-activity-invoice-band__identity py-1.5 pr-1 text-[var(--trk-text-muted)] align-middle"
        >
          <button
            type="button"
            className="px-1"
            aria-expanded={isExpanded}
            aria-label={`${isExpanded ? "Collapse" : "Expand"} invoice ${row.invoice_number}`}
            onClick={onToggle}
          >
            {isExpanded ? "▾" : "▸"}
          </button>
        </td>
        <td
          rowSpan={bandSize}
          className="fuel-activity-invoice-band__identity cursor-pointer py-1.5 pr-3 align-middle"
          onClick={onToggle}
        >
          {providerTableLabel(summary.provider_code)}
        </td>
        <td rowSpan={bandSize} className="fuel-activity-invoice-band__identity py-1.5 pr-3 font-medium align-middle">
          {onOpenProcessed ? (
            <button
              type="button"
              className="text-left font-medium text-[var(--trk-accent)] hover:underline"
              data-testid={`fuel-activity-invoice-link-${summary.batch_id}`}
              onClick={(e) => {
                e.stopPropagation();
                onOpenProcessed(summary.batch_id, summary.provider_code, summary.source_import_ref);
              }}
            >
              {row.invoice_number}
            </button>
          ) : (
            <span>{row.invoice_number}</span>
          )}
        </td>
        <td
          rowSpan={bandSize}
          className="fuel-activity-invoice-band__identity cursor-pointer py-1.5 pr-3 tabular-nums align-middle"
          onClick={onToggle}
          data-testid={`fuel-activity-card-${summary.batch_id}`}
        >
          {formatFuelActivityAccountCard(row)}
        </td>
        <td
          rowSpan={bandSize}
          className="fuel-activity-invoice-band__identity cursor-pointer py-1.5 pr-3 align-middle"
          onClick={onToggle}
        >
          {formatFuelActivityPeriod(row.period_start, row.period_end)}
        </td>
        <td
          rowSpan={bandSize}
          className="fuel-activity-invoice-band__identity cursor-pointer py-1.5 pr-3 align-middle"
          onClick={onToggle}
        >
          {formatFuelActivityDueDate(row.due_date)}
        </td>
        <td
          rowSpan={bandSize}
          className="fuel-activity-invoice-band__identity cursor-pointer py-1.5 pr-3 text-[var(--trk-text-muted)] align-middle"
          onClick={onToggle}
        >
          {fuelActivityPaymentLabel(row)}
        </td>
      </>
    );
  };

  const trailingCells = (lineIndex: number): ReactNode => {
    if (lineIndex !== 0) return null;
    return (
      <>
        <td
          rowSpan={bandSize}
          className="fuel-activity-invoice-band__identity py-1.5 pr-3 align-middle"
          data-testid={`fuel-activity-invoice-total-${summary.batch_id}`}
        >
          <InvoiceTotalStack lines={lines} />
        </td>
        <td rowSpan={bandSize} className="fuel-activity-invoice-band__identity py-1.5 text-right align-middle">
          {onOpenProcessed ? (
            <button
              type="button"
              className="font-medium text-[var(--trk-accent)] hover:underline"
              data-testid={`fuel-activity-open-${summary.batch_id}`}
              onClick={(e) => {
                e.stopPropagation();
                onOpenProcessed(summary.batch_id, summary.provider_code, summary.source_import_ref);
              }}
            >
              Open source
            </button>
          ) : null}
        </td>
      </>
    );
  };

  return (
    <>
      {bandLines.map((line, lineIndex) => {
        const isContinuation = lineIndex > 0;
        const isKnownLine = line.currency !== "—";
        return (
          <tr
            key={`${summary.batch_id}-${line.currency}-${lineIndex}`}
            data-testid={lineIndex === 0 ? `fuel-activity-invoice-${summary.batch_id}` : undefined}
            data-expanded={lineIndex === 0 ? (isExpanded ? "true" : "false") : undefined}
            data-currency-band={isKnownLine ? line.currency : undefined}
            className={`${rowClassBase}${isContinuation ? " fuel-activity-invoice-band__continuation" : ""}`}
          >
            {identityCells(lineIndex)}
            <td
              className={`fuel-activity-invoice-band__money cursor-pointer tabular-nums font-medium ${
                isContinuation ? "fuel-activity-invoice-band__money--continuation" : ""
              }`}
              onClick={onToggle}
              data-testid={
                isKnownLine ? `fuel-activity-currency-line-${line.currency}` : undefined
              }
            >
              {isKnownLine ? line.currency : "—"}
            </td>
            <td
              className={`fuel-activity-invoice-band__money cursor-pointer tabular-nums ${
                isContinuation ? "fuel-activity-invoice-band__money--continuation" : ""
              }`}
              onClick={onToggle}
            >
              {isKnownLine ? formatFuelCurrencyFinancialDiscount(line) : "—"}
            </td>
            <td
              className={`fuel-activity-invoice-band__money cursor-pointer tabular-nums ${
                isContinuation ? "fuel-activity-invoice-band__money--continuation" : ""
              }`}
              onClick={onToggle}
            >
              {isKnownLine ? formatFuelCurrencyFinancialTotal(line) : "—"}
            </td>
            {trailingCells(lineIndex)}
          </tr>
        );
      })}
    </>
  );
}

export default function FuelRecentActivitySection({
  activity,
  loading,
  heading = "Recent activity",
  showViewAllLink = true,
  onViewAllClick,
  emptyMessage = "No completed imports yet.",
  onOpenProcessed,
  highlightBatchId = null,
}: Props) {
  const [expandedBatchId, setExpandedBatchId] = useState<number | null>(null);

  const rows: FuelActivityRow[] = activity.map(fuelActivityRowFromProcessed);

  const toggleInvoice = useCallback((batchId: number) => {
    setExpandedBatchId((prev) => (prev === batchId ? null : batchId));
  }, []);

  return (
    <section
      className="fuel-recent-activity rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2"
      data-testid="fuel-recent-activity"
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
          {heading}
        </h2>
        {showViewAllLink ? (
          onViewAllClick ? (
            <button
              type="button"
              className="text-xs text-[var(--trk-accent)] hover:underline"
              onClick={onViewAllClick}
            >
              View all
            </button>
          ) : (
            <a href={OPS.FUEL} className="text-xs text-[var(--trk-accent)] hover:underline">
              View all
            </a>
          )
        ) : null}
      </div>
      {loading ? (
        <p className="text-xs text-[var(--trk-text-muted)]">Loading…</p>
      ) : activity.length === 0 ? (
        <p className="text-xs text-[var(--trk-text-muted)]">{emptyMessage}</p>
      ) : (
        <div className="trk-scroll-x fuel-recent-activity__scroll">
          <table className="fuel-recent-activity__table text-left text-xs">
            <thead className="text-[10px] uppercase text-[var(--trk-text-muted)]">
              <tr>
                <th className="w-6 py-1 pr-1" aria-hidden="true" />
                <th className="py-1 pr-3">Provider</th>
                <th className="py-1 pr-3">Invoice</th>
                <th className="py-1 pr-3">Account / Card</th>
                <th className="py-1 pr-3">Period</th>
                <th className="py-1 pr-3">Due Date</th>
                <th className="py-1 pr-3">Payment</th>
                <th className="py-1 pr-3">Cur</th>
                <th className="py-1 pr-3">Discount</th>
                <th className="py-1 pr-3">Total</th>
                <th className="py-1 pr-3">Invoice Total</th>
                <th className="py-1" />
              </tr>
            </thead>
            <tbody>
              {activity.map((summary, index) => {
                const row = rows[index]!;
                const isExpanded = expandedBatchId === summary.batch_id;
                return (
                  <Fragment key={summary.batch_id}>
                    <FuelActivityInvoiceBand
                      summary={summary}
                      row={row}
                      isExpanded={isExpanded}
                      highlighted={highlightBatchId === summary.batch_id}
                      onToggle={() => toggleInvoice(summary.batch_id)}
                      onOpenProcessed={onOpenProcessed}
                    />
                    {isExpanded ? (
                      <tr
                        key={`${summary.batch_id}-detail`}
                        className="border-t border-[var(--trk-border)] fuel-activity-invoice-band__detail"
                      >
                        <td colSpan={12} className="fuel-recent-activity__detail-cell bg-[var(--trk-bg)] px-2 py-2">
                          <div
                            className="fuel-activity-txn-contained min-w-0 max-w-full w-full overflow-x-auto"
                            data-testid={`fuel-activity-detail-${summary.batch_id}`}
                          >
                            <ProcessedFuelStatementShell
                              batchId={summary.batch_id}
                              providerCode={summary.provider_code}
                              providerLabel={providerTableLabel(summary.provider_code)}
                              invoiceNumber={summary.invoice_number}
                              transactionCount={summary.transaction_count}
                              controlCount={summary.control_count}
                              sourceImportRef={summary.source_import_ref}
                              currencyFinancialSummaries={summary.currency_financial_summaries}
                              providerControlTotals={summary.provider_control_totals}
                              onOpenSource={
                                summary.provider_code === "MANUAL_ENTRY"
                                  ? summary.source_storage_ref
                                    ? () => {
                                        window.open(
                                          fuelReviewBatchDocumentUrl(summary.batch_id),
                                          "_blank",
                                          "noopener,noreferrer",
                                        );
                                      }
                                    : undefined
                                  : onOpenProcessed
                                    ? () =>
                                        onOpenProcessed(
                                          summary.batch_id,
                                          summary.provider_code,
                                          summary.source_import_ref,
                                        )
                                    : undefined
                              }
                            />
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
