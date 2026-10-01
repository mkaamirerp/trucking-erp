import { Fragment, useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { getFuelBvdImportRows, type FuelBvdCompletedBasic, type FuelBvdRow } from "../../api";
import { OPS } from "../../routes";
import ProcessedStatementWorkspace from "./ProcessedStatementWorkspace";
import { parseBvdImportRowsForDashboard } from "./fuelRecentActivityRows";
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
import "../fuelBvdReview/bvd-parsed-statement.css";
import "./fuel-home.css";

type Props = {
  activity: FuelBvdCompletedBasic[];
  loading: boolean;
  /** Section title (default: Recent activity). */
  heading?: string;
  /** Show link to full history page (dashboard only). */
  showViewAllLink?: boolean;
  /** When set, View all expands on Fuel home instead of routing elsewhere. */
  onViewAllClick?: () => void;
  emptyMessage?: string;
  /** Open processed record in Fuel home overlay (normal flow). */
  onOpenProcessed?: (importId: string) => void;
  /** Brief highlight after Process (import_id). */
  highlightImportId?: string | null;
};

type LoadedInvoice = import("./fuelRecentActivityRows").FuelDashboardImportRows;

export default function FuelRecentActivitySection({
  activity,
  loading,
  heading = "Recent activity",
  showViewAllLink = true,
  onViewAllClick,
  emptyMessage = "No completed imports yet.",
  onOpenProcessed,
  highlightImportId = null,
}: Props) {
  const [expandedImportId, setExpandedImportId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<Record<string, LoadedInvoice>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingImportId, setLoadingImportId] = useState<string | null>(null);

  const toggleInvoice = useCallback(
    async (importId: string) => {
      if (expandedImportId === importId) {
        setExpandedImportId(null);
        return;
      }
      setExpandedImportId(importId);
      setLoadError(null);
      if (loaded[importId]) return;

      setLoadingImportId(importId);
      try {
        const rows = await getFuelBvdImportRows(importId);
        const parsed = parseBvdImportRowsForDashboard(rows);
        setLoaded((prev) => ({ ...prev, [importId]: parsed }));
      } catch (e: unknown) {
        setLoadError(e instanceof Error ? e.message : "Could not load transactions");
      } finally {
        setLoadingImportId(null);
      }
    },
    [expandedImportId, loaded],
  );

  const expandedData = expandedImportId ? loaded[expandedImportId] : null;

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
            <Link to={OPS.FUEL} className="text-xs text-[var(--trk-accent)] hover:underline">
              View all
            </Link>
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
              {activity.map((row) => {
                const isExpanded = expandedImportId === row.import_id;
                return (
                  <Fragment key={row.import_id}>
                    <tr
                      data-testid={`fuel-activity-invoice-${row.import_id}`}
                      data-expanded={isExpanded ? "true" : "false"}
                      className={`border-t border-[var(--trk-border)]${
                        isExpanded ? " bg-[var(--trk-surface-2)]/50" : ""
                      }${highlightImportId === row.import_id ? " ring-1 ring-inset ring-[var(--trk-success)]" : ""}`}
                    >
                      <td className="py-1.5 pr-1 text-[var(--trk-text-muted)]">
                        <button
                          type="button"
                          className="px-1"
                          aria-expanded={isExpanded}
                          aria-label={`${isExpanded ? "Collapse" : "Expand"} invoice ${row.invoice_number}`}
                          onClick={() => void toggleInvoice(row.import_id)}
                        >
                          {isExpanded ? "▾" : "▸"}
                        </button>
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3"
                        onClick={() => void toggleInvoice(row.import_id)}
                      >
                        {row.provider}
                      </td>
                      <td className="py-1.5 pr-3 font-medium">
                        {onOpenProcessed ? (
                          <button
                            type="button"
                            className="text-left font-medium text-[var(--trk-accent)] hover:underline"
                            data-testid={`fuel-activity-invoice-link-${row.import_id}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              onOpenProcessed(row.import_id);
                            }}
                          >
                            {row.invoice_number}
                          </button>
                        ) : (
                          <Link
                            to={OPS.FUEL_BVD_DETAIL(row.import_id)}
                            className="text-[var(--trk-accent)] hover:underline"
                            data-testid={`fuel-activity-invoice-link-${row.import_id}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {row.invoice_number}
                          </Link>
                        )}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 tabular-nums"
                        onClick={() => void toggleInvoice(row.import_id)}
                        data-testid={`fuel-activity-card-${row.import_id}`}
                      >
                        {formatFuelActivityAccountCard(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3"
                        onClick={() => void toggleInvoice(row.import_id)}
                        data-testid={`fuel-activity-period-${row.import_id}`}
                      >
                        {formatFuelActivityPeriod(row.period_start, row.period_end)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3"
                        onClick={() => void toggleInvoice(row.import_id)}
                        data-testid={`fuel-activity-due-${row.import_id}`}
                      >
                        {formatFuelActivityDueDate(row.due_date)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 text-[var(--trk-text-muted)]"
                        onClick={() => void toggleInvoice(row.import_id)}
                        data-testid={`fuel-activity-payment-${row.import_id}`}
                      >
                        {fuelActivityPaymentLabel(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 tabular-nums"
                        onClick={() => void toggleInvoice(row.import_id)}
                        data-testid={`fuel-activity-discount-${row.import_id}`}
                      >
                        {formatFuelActivityInvoiceDiscount(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 tabular-nums"
                        onClick={() => void toggleInvoice(row.import_id)}
                        data-testid={`fuel-activity-cad-total-${row.import_id}`}
                      >
                        {formatFuelActivityCadTotal(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 tabular-nums"
                        onClick={() => void toggleInvoice(row.import_id)}
                        data-testid={`fuel-activity-usd-total-${row.import_id}`}
                      >
                        {formatFuelActivityUsdTotal(row)}
                      </td>
                      <td
                        className="cursor-pointer py-1.5 pr-3 tabular-nums font-medium"
                        onClick={() => void toggleInvoice(row.import_id)}
                        data-testid={`fuel-activity-invoice-total-${row.import_id}`}
                        data-source-currency={row.currency ?? ""}
                      >
                        {formatFuelActivityInvoiceTotal(row)}
                      </td>
                      <td className="py-1.5 text-right">
                        {onOpenProcessed ? (
                          <button
                            type="button"
                            className="font-medium text-[var(--trk-accent)] hover:underline"
                            data-testid={`fuel-activity-open-${row.import_id}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              onOpenProcessed(row.import_id);
                            }}
                          >
                            Open
                          </button>
                        ) : (
                          <Link
                            to={OPS.FUEL_BVD_DETAIL(row.import_id)}
                            className="font-medium text-[var(--trk-accent)] hover:underline"
                            data-testid={`fuel-activity-open-${row.import_id}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            Open
                          </Link>
                        )}
                      </td>
                    </tr>
                    {isExpanded ? (
                      <tr key={`${row.import_id}-detail`} className="border-t border-[var(--trk-border)]">
                        <td colSpan={12} className="fuel-recent-activity__detail-cell bg-[var(--trk-bg)] px-2 py-2">
                          {loadError && expandedImportId === row.import_id ? (
                            <p className="text-xs text-[var(--trk-danger)]" role="alert">{loadError}</p>
                          ) : null}
                          {loadingImportId === row.import_id ? (
                            <p className="text-xs text-[var(--trk-text-muted)]">Loading transactions…</p>
                          ) : expandedData && expandedData.chargeCount > 0 ? (
                            <div
                              className="fuel-activity-txn-contained min-w-0 max-w-full w-full"
                              data-testid={`fuel-activity-txn-scroll-${row.import_id}`}
                            >
                            <ProcessedStatementWorkspace
                              importId={row.import_id}
                              sourceRows={expandedData.sourceRows}
                              invoiceNumber={row.invoice_number}
                              invoiceTotal={row.total_amount}
                              currency={row.currency}
                              cardNumber={expandedData.cardNumber || row.card_number || ""}
                              fullInvoiceLink={
                                onOpenProcessed ? (
                                  <button
                                    type="button"
                                    className="text-xs font-medium text-[var(--trk-accent)] hover:underline"
                                    data-testid={`fuel-activity-full-invoice-${row.import_id}`}
                                    onClick={() => onOpenProcessed(row.import_id)}
                                  >
                                    Open full invoice
                                  </button>
                                ) : (
                                  <Link
                                    to={OPS.FUEL_BVD_DETAIL(row.import_id)}
                                    className="text-xs font-medium text-[var(--trk-accent)] hover:underline"
                                    data-testid={`fuel-activity-full-invoice-${row.import_id}`}
                                  >
                                    Open full invoice
                                  </Link>
                                )
                              }
                            />
                            </div>
                          ) : expandedData && expandedData.chargeCount === 0 ? (
                            <p className="text-xs text-[var(--trk-text-muted)]">No accepted charges on this invoice.</p>
                          ) : null}
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
