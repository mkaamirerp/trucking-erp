import { useEffect, useMemo, useState, type ReactNode } from "react";
import { getFuelBvdCanonicalTransactions, type FuelBvdRow, type FuelCanonicalTransaction } from "../../api";
import BvdExpressRowsTable from "../fuelBvdReview/BvdExpressRowsTable";
import BvdTransactionRowsTable from "../fuelBvdReview/BvdTransactionRowsTable";
import {
  buildStatementMonthGroups,
  parseBvdStatementTransactionDate,
  type DatePeriodSelection,
} from "../fuelBvdReview/fuelProcessedStatementDateFilter";
import {
  buildCanonicalByBvdRowId,
  filterProcessedStatementRows,
} from "../fuelBvdReview/fuelProcessedStatementSearch";
import ProcessedStatementFilterBar from "../fuelBvdReview/ProcessedStatementFilterBar";
import { operationalCell } from "../fuelBvdReview/bvdParsedDisplay";
import {
  allProcessedStatementSearchableRows,
  splitProcessedStatementCharges,
} from "./processedStatementCharges";
import { formatProcessedMoneyTotal, sumProcessedChargeFinalAmount } from "./processedStatementMoney";

type Props = {
  importId: string;
  /** All permanent fuel_bvd rows for this import (charge sections derived client-side). */
  sourceRows: FuelBvdRow[];
  cardNumber: string;
  invoiceNumber: string;
  invoiceTotal?: string | null;
  currency?: string | null;
  fullInvoiceLink: ReactNode;
};

export default function ProcessedStatementWorkspace({
  importId,
  sourceRows,
  cardNumber,
  invoiceNumber,
  invoiceTotal,
  currency,
  fullInvoiceLink,
}: Props) {
  const [searchQuery, setSearchQuery] = useState("");
  const [datePeriod, setDatePeriod] = useState<DatePeriodSelection>({ kind: "all" });
  const [canonical, setCanonical] = useState<FuelCanonicalTransaction[]>([]);

  const sections = useMemo(() => splitProcessedStatementCharges(sourceRows), [sourceRows]);
  const searchableRows = useMemo(() => allProcessedStatementSearchableRows(sections), [sections]);

  useEffect(() => {
    setSearchQuery("");
    setDatePeriod({ kind: "all" });
    let cancelled = false;
    getFuelBvdCanonicalTransactions(importId)
      .then((rows) => {
        if (!cancelled) setCanonical(rows);
      })
      .catch(() => {
        if (!cancelled) setCanonical([]);
      });
    return () => {
      cancelled = true;
    };
  }, [importId]);

  const searchCtx = useMemo(
    () => ({
      headerCardNumber: cardNumber,
      canonicalByRowId: buildCanonicalByBvdRowId(searchableRows, canonical),
    }),
    [cardNumber, searchableRows, canonical],
  );

  const monthGroups = useMemo(() => {
    const dates = searchableRows
      .map((r) => parseBvdStatementTransactionDate(operationalCell(r, "transaction_date")))
      .filter((d): d is Date => d !== null);
    return buildStatementMonthGroups(dates);
  }, [searchableRows]);

  const filteredCard = useMemo(
    () => filterProcessedStatementRows(sections.cardTransactions, searchQuery, datePeriod, searchCtx),
    [sections.cardTransactions, searchQuery, datePeriod, searchCtx],
  );

  const filteredExpress = useMemo(
    () => filterProcessedStatementRows(sections.expressCharges, searchQuery, datePeriod, searchCtx),
    [sections.expressCharges, searchQuery, datePeriod, searchCtx],
  );

  const filteredCount = filteredCard.length + filteredExpress.length;
  const cardTotal = sumProcessedChargeFinalAmount(sections.cardTransactions);
  const expressTotal = sumProcessedChargeFinalAmount(sections.expressCharges);
  const combinedTotal = cardTotal + expressTotal;
  const displayCurrency = (currency?.trim() || operationalCell(searchableRows[0] ?? ({} as FuelBvdRow), "cur") || "—").trim();

  return (
    <div data-testid={`fuel-processed-statement-${importId}`}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="processed-statement-summary min-w-0" data-testid="processed-statement-summary">
          <div className="text-xs font-bold uppercase tracking-wide text-[var(--trk-text)]">
            BVD {invoiceNumber}
          </div>
          <div className="text-[11px] font-semibold text-[var(--trk-text-muted)]" data-testid="processed-charge-count">
            {sections.chargeCount} charges
          </div>
          <div className="processed-statement-summary-lines">
            {sections.cardTransactions.length > 0 ? (
              <div
                className="processed-statement-summary-line"
                data-testid="processed-card-section-total"
              >
                <span className="processed-statement-summary-line__label">Fuel / Card Transactions</span>
                <span className="processed-statement-summary-line__count">
                  {sections.cardTransactions.length}
                </span>
                <span className="processed-statement-summary-line__amount">
                  {formatProcessedMoneyTotal(cardTotal)}
                </span>
              </div>
            ) : null}
            {sections.expressCharges.length > 0 ? (
              <div
                className="processed-statement-summary-line"
                data-testid="processed-express-section-total"
              >
                <span className="processed-statement-summary-line__label">Express Charges</span>
                <span className="processed-statement-summary-line__count">
                  {sections.expressCharges.length}
                </span>
                <span className="processed-statement-summary-line__amount">
                  {formatProcessedMoneyTotal(expressTotal)}
                </span>
              </div>
            ) : null}
            <div
              className="processed-statement-summary-line processed-statement-summary-line--total"
              data-testid="processed-invoice-total"
            >
              <span className="processed-statement-summary-line__label">Processed Invoice Total</span>
              <span className="processed-statement-summary-line__count" aria-hidden="true" />
              <span className="processed-statement-summary-line__amount">
                {invoiceTotal?.trim() || formatProcessedMoneyTotal(combinedTotal)}
                {displayCurrency ? ` ${displayCurrency}` : ""}
              </span>
            </div>
          </div>
        </div>
        <div className="shrink-0">{fullInvoiceLink}</div>
      </div>

      <ProcessedStatementFilterBar
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        period={datePeriod}
        onPeriodChange={setDatePeriod}
        monthGroups={monthGroups}
        filteredCount={filteredCount}
        totalCount={sections.chargeCount}
        onClear={() => {
          setSearchQuery("");
          setDatePeriod({ kind: "all" });
        }}
      />

      {sections.cardTransactions.length > 0 ? (
        <section
          className="processed-statement-section processed-statement-section--charges mb-2"
          aria-label="Fuel and card transactions"
        >
          <BvdTransactionRowsTable
            transactions={filteredCard}
            cardNumber={cardNumber}
            processedStickyHeader
          />
        </section>
      ) : null}

      {sections.expressCharges.length > 0 ? (
        <section
          className="processed-statement-section processed-statement-section--charges"
          aria-label="Express charges"
        >
          <h3
            className="mb-1 text-[10px] font-bold uppercase tracking-wide text-[var(--trk-text-muted)]"
            data-testid="processed-express-section-label"
          >
            Express Charges
          </h3>
          <BvdExpressRowsTable
            rows={filteredExpress}
            canonicalByRowId={searchCtx.canonicalByRowId}
            processedStickyHeader
          />
        </section>
      ) : null}
    </div>
  );
}
