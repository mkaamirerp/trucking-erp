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
  const filteredCardTotal = sumProcessedChargeFinalAmount(filteredCard);
  const filteredExpressTotal = sumProcessedChargeFinalAmount(filteredExpress);

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
          {sections.cardTransactions.length > 0 ? (
            <div className="text-[11px] text-[var(--trk-text)]" data-testid="processed-card-section-total">
              Fuel / Card Transactions ({sections.cardTransactions.length}) = {formatProcessedMoneyTotal(cardTotal)}
            </div>
          ) : null}
          {sections.expressCharges.length > 0 ? (
            <div className="text-[11px] text-[var(--trk-text)]" data-testid="processed-express-section-total">
              Express Charges ({sections.expressCharges.length}) = {formatProcessedMoneyTotal(expressTotal)}
            </div>
          ) : null}
          <div className="text-[11px] font-semibold text-[var(--trk-text)]" data-testid="processed-invoice-total">
            Processed Invoice Total = {invoiceTotal?.trim() || formatProcessedMoneyTotal(combinedTotal)}
            {displayCurrency ? ` ${displayCurrency}` : ""}
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
        <section className="processed-statement-section mb-3" aria-label="Fuel and card transactions">
          <h3
            className="mb-1 text-[11px] font-bold uppercase tracking-wide text-[var(--trk-text-muted)]"
            data-testid="processed-card-section-heading"
          >
            Fuel / Card Transactions ({filteredCard.length}
            {filteredCard.length !== sections.cardTransactions.length
              ? ` of ${sections.cardTransactions.length}`
              : ""}
            ) — {formatProcessedMoneyTotal(filteredCardTotal)}
          </h3>
          <BvdTransactionRowsTable transactions={filteredCard} cardNumber={cardNumber} />
        </section>
      ) : null}

      {sections.expressCharges.length > 0 ? (
        <section className="processed-statement-section" aria-label="Express charges">
          <h3
            className="mb-1 text-[11px] font-bold uppercase tracking-wide text-[var(--trk-text-muted)]"
            data-testid="processed-express-section-heading"
          >
            Express Charges ({filteredExpress.length}
            {filteredExpress.length !== sections.expressCharges.length
              ? ` of ${sections.expressCharges.length}`
              : ""}
            ) — {formatProcessedMoneyTotal(filteredExpressTotal)}
          </h3>
          <BvdExpressRowsTable rows={filteredExpress} canonicalByRowId={searchCtx.canonicalByRowId} />
        </section>
      ) : null}
    </div>
  );
}
