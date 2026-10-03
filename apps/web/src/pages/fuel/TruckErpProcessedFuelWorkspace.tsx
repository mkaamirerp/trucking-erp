import { useEffect, useState } from "react";
import {
  getFuelBvdImportRows,
  getFuelNationwideImportRows,
  getFuelProcessedBatch,
  type FuelBvdRow,
  type FuelCanonicalTransaction,
  type FuelProcessedCurrencyFinancial,
  type FuelProcessedCurrencyTotal,
} from "../../api";
import ProcessedStatementWorkspace from "./ProcessedStatementWorkspace";
import { parseBvdImportRowsForDashboard } from "./fuelRecentActivityRows";
import {
  adaptNationwideImportRowsForProcessedStatement,
  applyNationwideCanonicalPricesToStatementRows,
} from "./nationwideProcessedStatementAdapter";

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

  useEffect(() => {
    if (!sourceImportRef) {
      setError("Source import reference missing");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    const code = providerCode.toUpperCase();
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

        if (code === "BVD") {
          const rows = await getFuelBvdImportRows(sourceImportRef);
          const parsed = parseBvdImportRowsForDashboard(rows);
          setSourceRows(parsed.sourceRows);
          setCardNumber(parsed.cardNumber);
          return;
        }
        if (code === "NATIONWIDE") {
          const rows = await getFuelNationwideImportRows(sourceImportRef);
          const operational = applyNationwideCanonicalPricesToStatementRows(
            adaptNationwideImportRowsForProcessedStatement(rows),
            detail.canonical_transactions,
          );
          setSourceRows(operational);
          const header = rows.find((r) => r.row_type === "HEADER");
          setCardNumber(header?.card_number?.trim() || operational[0]?.card_number?.trim() || "");
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
  if (!sourceImportRef || sourceRows.length === 0) {
    return <p className="text-xs text-[var(--trk-text-muted)]">No operational transactions for this batch.</p>;
  }

  return (
    <ProcessedStatementWorkspace
      importId={sourceImportRef}
      sourceRows={sourceRows}
      cardNumber={cardNumber}
      invoiceNumber={invoiceNumber}
      invoiceTotal={invoiceTotal}
      currency={displayCurrency}
      providerLabel={providerLabel}
      canonicalTransactions={canonical}
      currencyFinancialSummaries={currencyFinancialSummaries}
      providerControlTotals={providerControlTotals}
    />
  );
}
