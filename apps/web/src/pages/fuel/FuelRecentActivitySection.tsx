import { Fragment, useCallback, useState } from "react";
import type { FuelProcessedSummary } from "../../api";
import { OPS } from "../../routes";
import { fuelActivityRowFromProcessed, type FuelActivityRow } from "./fuelActivityRow";
import {
  formatFuelActivityCadTotal,
  formatFuelActivityDueDate,
  formatFuelActivityInvoiceDiscount,
  formatFuelActivityInvoiceTotal,
  formatFuelActivityPeriod,
  formatFuelActivityUsdTotal,
  formatFuelActivityAccountCard,
  fuelActivityPaymentLabel,
} from "./fuelActivityInvoiceDisplay";
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
  return code;
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
                <th className="py-1 pr-3">Discount</th>
                <th className="py-1 pr-3">CAD Total</th>
                <th className="py-1 pr-3">USD Total</th>
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
                    <tr
                      data-testid={`fuel-activity-invoice-${summary.batch_id}`}
                      data-expanded={isExpanded ? "true" : "false"}
                      className={`border-t border-[var(--trk-border)]${
                        isExpanded ? " bg-[var(--trk-surface-2)]/50" : ""
                      }${highlightBatchId === summary.batch_id ? " ring-1 ring-inset ring-[var(--trk-success)]" : ""}`}
                    >
                      <td className="py-1.5 pr-1 text-[var(--trk-text-muted)]">
                        <button
                          type="button"
                          className="px-1"
                          aria-expanded={isExpanded}
                          aria-label={`${isExpanded ? "Collapse" : "Expand"} invoice ${row.invoice_number}`}
                          onClick={() => toggleInvoice(summary.batch_id)}
                        >
                          {isExpanded ? "▾" : "▸"}
                        </button>
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3"
                        onClick={() => toggleInvoice(summary.batch_id)}
                      >
                        {providerTableLabel(summary.provider_code)}
                      </td>
                      <td className="py-1.5 pr-3 font-medium">
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
                        className="cursor-pointer py-1.5 pr-3 tabular-nums"
                        onClick={() => toggleInvoice(summary.batch_id)}
                        data-testid={`fuel-activity-card-${summary.batch_id}`}
                      >
                        {formatFuelActivityAccountCard(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3"
                        onClick={() => toggleInvoice(summary.batch_id)}
                      >
                        {formatFuelActivityPeriod(row.period_start, row.period_end)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3"
                        onClick={() => toggleInvoice(summary.batch_id)}
                      >
                        {formatFuelActivityDueDate(row.due_date)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 text-[var(--trk-text-muted)]"
                        onClick={() => toggleInvoice(summary.batch_id)}
                      >
                        {fuelActivityPaymentLabel(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 tabular-nums"
                        onClick={() => toggleInvoice(summary.batch_id)}
                      >
                        {formatFuelActivityCadTotal(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 tabular-nums"
                        onClick={() => toggleInvoice(summary.batch_id)}
                      >
                        {formatFuelActivityUsdTotal(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 tabular-nums font-medium"
                        onClick={() => toggleInvoice(summary.batch_id)}
                      >
                        {formatFuelActivityInvoiceTotal(row)}
                      </td>
                      <td className="py-1.5 text-right">
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
                            Open
                          </button>
                        ) : null}
                      </td>
                    </tr>
                    {isExpanded ? (
                      <tr key={`${summary.batch_id}-detail`} className="border-t border-[var(--trk-border)]">
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
                              onOpenFull={
                                onOpenProcessed
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
