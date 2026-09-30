import { useEffect, useMemo, useState, type ReactNode } from "react";
import { getFuelBvdCanonicalTransactions, type FuelBvdRow, type FuelCanonicalTransaction } from "../../api";
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

type Props = {
  importId: string;
  transactions: FuelBvdRow[];
  cardNumber: string;
  fullInvoiceLink: ReactNode;
};

export default function RecentActivityStatementTxnPanel({
  importId,
  transactions,
  cardNumber,
  fullInvoiceLink,
}: Props) {
  const [searchQuery, setSearchQuery] = useState("");
  const [datePeriod, setDatePeriod] = useState<DatePeriodSelection>({ kind: "all" });
  const [canonical, setCanonical] = useState<FuelCanonicalTransaction[]>([]);

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
      canonicalByRowId: buildCanonicalByBvdRowId(transactions, canonical),
    }),
    [cardNumber, transactions, canonical],
  );

  const monthGroups = useMemo(() => {
    const dates = transactions
      .map((r) => parseBvdStatementTransactionDate(operationalCell(r, "transaction_date")))
      .filter((d): d is Date => d !== null);
    return buildStatementMonthGroups(dates);
  }, [transactions]);

  const filteredTransactions = useMemo(
    () => filterProcessedStatementRows(transactions, searchQuery, datePeriod, searchCtx),
    [transactions, searchQuery, datePeriod, searchCtx],
  );

  return (
    <div data-testid={`fuel-activity-txn-panel-${importId}`}>
      <div className="mb-2 flex flex-wrap items-center justify-end gap-2">{fullInvoiceLink}</div>
      <ProcessedStatementFilterBar
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        period={datePeriod}
        onPeriodChange={setDatePeriod}
        monthGroups={monthGroups}
        filteredCount={filteredTransactions.length}
        totalCount={transactions.length}
        onClear={() => {
          setSearchQuery("");
          setDatePeriod({ kind: "all" });
        }}
      />
      <BvdTransactionRowsTable transactions={filteredTransactions} cardNumber={cardNumber} />
    </div>
  );
}
