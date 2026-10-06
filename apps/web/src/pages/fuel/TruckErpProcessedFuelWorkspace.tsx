import { useEffect, useState } from "react";
import {
  getFuelBvdImportRows,
  getFuelNationwideImportRows,
  getFuelNationwideSourceReconciliation,
  getFuelProcessedBatch,
  type FuelBvdRow,
  type FuelCanonicalTransaction,
  type FuelProcessedCurrencyFinancial,
  type FuelProcessedCurrencyTotal,
  type FuelProcessedOperationalTransaction,
} from "../../api";
import ProcessedStatementWorkspace from "./ProcessedStatementWorkspace";
import { parseBvdImportRowsForDashboard } from "./fuelRecentActivityRows";
import { applyOperationalQuantityUnitToStatementRows } from "./fuelTxnQuantityDisplay";
import {
  adaptNationwideImportRowsForProcessedStatement,
  applyNationwideCanonicalPricesToStatementRows,
} from "./nationwideProcessedStatementAdapter";
import { adaptManualOperationalTransactionsForProcessedStatement } from "./manualProcessedStatementAdapter";

type Props = {
  batchId: number;
  providerCode: string;
  providerLabel: string;
  invoiceNumber: string;
  sourceImportRef: string | null;
  currencyFinancialSummaries?: FuelProcessedCurrencyFinancial[];
  providerControlTotals?: FuelProcessedCurrencyTotal[];
};

export default function TruckErpProcessedFuelWorkspace({
  batchId,
  providerCode,
  providerLabel,
  invoiceNumber,
  sourceImportRef,
  currencyFinancialSummaries: currencyFinancialSummariesProp,
  providerControlTotals: providerControlTotalsProp,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [canonical, setCanonical] = useState<FuelCanonicalTransaction[]>([]);
  const [sourceRows, setSourceRows] = useState<FuelBvdRow[]>([]);
  const [cardNumber, setCardNumber] = useState("");
  const [invoiceTotal, setInvoiceTotal] = useState<string | null>(null);
  const [displayCurrency, setDisplayCurrency] = useState<string | null>(null);
  const [currencyFinancialSummaries, setCurrencyFinancialSummaries] = useState<
    FuelProcessedCurrencyFinancial[]
  >(currencyFinancialSummariesProp ?? []);
  const [providerControlTotals, setProviderControlTotals] = useState<FuelProcessedCurrencyTotal[]>(
    providerControlTotalsProp ?? [],
  );
  const [manualOperationalTransaction, setManualOperationalTransaction] =
    useState<FuelProcessedOperationalTransaction | null>(null);

  useEffect(() => {
    const code = providerCode.toUpperCase();
    if (!sourceImportRef && code !== "MANUAL_ENTRY") {
      setError("Source import reference missing");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setSourceRows([]);
    setManualOperationalTransaction(null);
    void getFuelProcessedBatch(batchId)
      .then(async (detail) => {
        setCanonical(detail.canonical_transactions);
        setCurrencyFinancialSummaries(
          detail.currency_financial_summaries?.length
            ? detail.currency_financial_summaries
            : currencyFinancialSummariesProp ?? [],
        );
        setProviderControlTotals(
          detail.provider_control_totals?.length
            ? detail.provider_control_totals
            : providerControlTotalsProp ?? [],
        );
        if (detail.total_amount) {
          setInvoiceTotal(detail.total_amount);
        } else if (detail.cad_transaction_total) {
          setInvoiceTotal(detail.cad_transaction_total);
          setDisplayCurrency("CAD");
        } else if (detail.usd_transaction_total) {
          setInvoiceTotal(detail.usd_transaction_total);
          setDisplayCurrency("USD");
        }
        if (detail.currency) setDisplayCurrency(detail.currency);

        const withQuantityUnits = (gridRows: FuelBvdRow[]) =>
          applyOperationalQuantityUnitToStatementRows(gridRows, detail.operational_transactions ?? []);

        if (code === "BVD") {
          const rows = await getFuelBvdImportRows(sourceImportRef);
          const parsed = parseBvdImportRowsForDashboard(rows);
          setSourceRows(withQuantityUnits(parsed.sourceRows));
          setCardNumber(parsed.cardNumber);
          return;
        }
        if (code === "NATIONWIDE") {
          const [rows, sourceReconciliation] = await Promise.all([
            getFuelNationwideImportRows(sourceImportRef!),
            getFuelNationwideSourceReconciliation(sourceImportRef!).catch(() => null),
          ]);
          const operationalRows = applyNationwideCanonicalPricesToStatementRows(
            adaptNationwideImportRowsForProcessedStatement(rows, sourceReconciliation),
            detail.canonical_transactions,
          );
          setSourceRows(withQuantityUnits(operationalRows));
          const header = rows.find((r) => r.row_type === "HEADER");
          setCardNumber(header?.card_number?.trim() || operationalRows[0]?.card_number?.trim() || "");
          return;
        }
        if (code === "MANUAL_ENTRY") {
          const operationalRows = adaptManualOperationalTransactionsForProcessedStatement(
            detail.operational_transactions ?? [],
            detail.source_import_ref,
          );
          setSourceRows(withQuantityUnits(operationalRows));
          setCardNumber(operationalRows[0]?.card_number?.trim() || detail.account_reference?.trim() || "");
          setManualOperationalTransaction(detail.operational_transactions?.[0] ?? null);
          return;
        }
        setError(`No operational workspace adapter for ${providerCode}`);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load processed workspace"))
      .finally(() => setLoading(false));
  }, [batchId, providerCode, sourceImportRef]);

  if (loading) {
    return <p className="text-xs text-[var(--trk-text-muted)]">Loading processed Fuel workspace…</p>;
  }
  if (error) {
    return <p className="text-xs text-[var(--trk-danger)]" role="alert">{error}</p>;
  }
  if (sourceRows.length === 0) {
    return <p className="text-xs text-[var(--trk-text-muted)]">No operational transactions for this batch.</p>;
  }

  return (
    <ProcessedStatementWorkspace
      importId={sourceImportRef ?? String(batchId)}
      sourceRows={sourceRows}
      cardNumber={cardNumber}
      invoiceNumber={invoiceNumber}
      invoiceTotal={invoiceTotal}
      currency={displayCurrency}
      providerLabel={providerLabel}
      manualOperationalTransaction={manualOperationalTransaction}
      canonicalTransactions={canonical}
      currencyFinancialSummaries={currencyFinancialSummaries}
      providerControlTotals={providerControlTotals}
    />
  );
}
