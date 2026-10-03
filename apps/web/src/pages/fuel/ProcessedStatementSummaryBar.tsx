import type { FuelBvdRow, FuelCanonicalTransaction, FuelProcessedCurrencyTotal } from "../../api";
import {
  formatFuelCurrencyFinancialDiscount,
  type FuelCurrencyFinancialLine,
} from "./fuelActivityCurrencyFinancial";
import {
  countFuelTransactionsByCurrency,
  formatProcessedPanelMoney,
  providerControlVarianceLabel,
} from "./fuelProcessedCurrencyPanel";

type Props = {
  currencyLines: FuelCurrencyFinancialLine[];
  canonicalTransactions: FuelCanonicalTransaction[];
  cardTransactionRows: FuelBvdRow[];
  providerControlTotals: FuelProcessedCurrencyTotal[];
  expressChargeCount: number;
  processedInvoiceTotalLabel: string;
};

export default function ProcessedStatementSummaryBar({
  currencyLines,
  canonicalTransactions,
  cardTransactionRows,
  providerControlTotals,
  expressChargeCount,
  processedInvoiceTotalLabel,
}: Props) {
  const txnCounts = countFuelTransactionsByCurrency(
    currencyLines,
    canonicalTransactions,
    cardTransactionRows,
  );

  if (currencyLines.length === 0) {
    return (
      <section className="fuel-currency-panel" data-testid="processed-statement-summary-bar">
        <div className="fuel-currency-panel__fallback tabular-nums" data-testid="processed-invoice-total">
          {processedInvoiceTotalLabel}
        </div>
        {expressChargeCount > 0 ? (
          <p className="fuel-currency-panel__express" data-testid="processed-express-section-total">
            Express charges: {expressChargeCount}
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <section className="fuel-currency-panel" aria-label="Statement totals by currency" data-testid="processed-statement-summary-bar">
      <div className="fuel-currency-panel__head">
        <span aria-hidden="true" />
        <span>Txns</span>
        <span>Discount</span>
        <span>Total</span>
        <span aria-hidden="true" />
      </div>
      {currencyLines.map((line, index) => {
        const variance = providerControlVarianceLabel(
          line.currency,
          line.total_amount,
          providerControlTotals,
        );
        return (
          <div
            key={line.currency}
            className={`fuel-currency-panel__row${
              index > 0 ? " fuel-currency-panel__row--continuation" : ""
            }`}
            data-testid={`processed-currency-summary-${line.currency}`}
          >
            <span className="fuel-currency-panel__ccy">{line.currency}</span>
            <span
              className="fuel-currency-panel__num tabular-nums"
              data-testid={index === 0 ? "processed-card-section-total" : undefined}
            >
              {txnCounts[line.currency] ?? 0}
            </span>
            <span className="fuel-currency-panel__num tabular-nums">
              {formatFuelCurrencyFinancialDiscount(line)}
            </span>
            <span className="fuel-currency-panel__num fuel-currency-panel__total tabular-nums">
              {formatProcessedPanelMoney(line.total_amount)}
            </span>
            <span className="fuel-currency-panel__note">{variance ?? ""}</span>
          </div>
        );
      })}
      {expressChargeCount > 0 ? (
        <p className="fuel-currency-panel__express" data-testid="processed-express-section-total">
          Express charges: {expressChargeCount}
        </p>
      ) : null}
    </section>
  );
}
