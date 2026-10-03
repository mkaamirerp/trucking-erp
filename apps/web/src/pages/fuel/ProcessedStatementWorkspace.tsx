import { useEffect, useMemo, useState } from "react";
import {
  getFuelBvdCanonicalTransactions,
  type FuelBvdRow,
  type FuelCanonicalTransaction,
  type FuelProcessedCurrencyFinancial,
  type FuelProcessedCurrencyTotal,
} from "../../api";
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
import {
  formatFuelActivityInvoiceTotalFromCurrencySummaries,
  fuelCurrencyFinancialFromApi,
  type FuelCurrencyFinancialLine,
} from "./fuelActivityCurrencyFinancial";
import ProcessedStatementSummaryBar from "./ProcessedStatementSummaryBar";
import { formatProcessedMoneyTotal, sumProcessedChargeFinalAmount } from "./processedStatementMoney";

type Props = {
  importId: string;
  /** All permanent fuel_bvd rows for this import (charge sections derived client-side). */
  sourceRows: FuelBvdRow[];
  cardNumber: string;
  invoiceNumber: string;
  invoiceTotal?: string | null;
  currency?: string | null;
  /** TruckERP provider label (not a separate provider UI). */
  providerLabel?: string;
  /** When set, skip per-import BVD canonical fetch (processed batch read model). */
  canonicalTransactions?: FuelCanonicalTransaction[];
  currencyFinancialSummaries?: FuelProcessedCurrencyFinancial[];
  providerControlTotals?: FuelProcessedCurrencyTotal[];
};

export default function ProcessedStatementWorkspace({
  importId,
  sourceRows,
  cardNumber,
  invoiceNumber,
  invoiceTotal,
  currency,
  providerLabel = "BVD",
  canonicalTransactions,
  currencyFinancialSummaries,
  providerControlTotals = [],
}: Props) {
  const [searchQuery, setSearchQuery] = useState("");
  const [datePeriod, setDatePeriod] = useState<DatePeriodSelection>({ kind: "all" });
  const [canonical, setCanonical] = useState<FuelCanonicalTransaction[]>(canonicalTransactions ?? []);

  const sections = useMemo(() => splitProcessedStatementCharges(sourceRows), [sourceRows]);
  const searchableRows = useMemo(() => allProcessedStatementSearchableRows(sections), [sections]);

  useEffect(() => {
    setSearchQuery("");
    setDatePeriod({ kind: "all" });
    if (canonicalTransactions) {
      setCanonical(canonicalTransactions);
      return;
    }
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
  }, [importId, canonicalTransactions]);

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
  const currencyLines: FuelCurrencyFinancialLine[] = fuelCurrencyFinancialFromApi(
    currencyFinancialSummaries,
  );
  const processedInvoiceTotalLabel =
    currencyLines.length > 0
      ? formatFuelActivityInvoiceTotalFromCurrencySummaries(currencyLines)
      : invoiceTotal?.trim()
        ? `${invoiceTotal.trim()}${currency ? ` ${currency}` : ""}`
        : `${formatProcessedMoneyTotal(combinedTotal)}${displayCurrency ? ` ${displayCurrency}` : ""}`;

  return (
    <div
      className="truckerp-processed-fuel-workspace"
      data-testid="truckerp-processed-fuel-workspace"
      data-provider={providerLabel}
    >
      <div data-testid={`fuel-processed-statement-${importId}`}>
      <div data-testid="processed-statement-summary">
        <ProcessedStatementSummaryBar
          currencyLines={currencyLines}
          canonicalTransactions={canonical}
          cardTransactionRows={sections.cardTransactions}
          providerControlTotals={providerControlTotals}
          expressChargeCount={sections.expressCharges.length}
          processedInvoiceTotalLabel={processedInvoiceTotalLabel}
        />
        <div className="sr-only" data-testid="processed-charge-count">{sections.chargeCount} charges</div>
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
    </div>
  );
}
