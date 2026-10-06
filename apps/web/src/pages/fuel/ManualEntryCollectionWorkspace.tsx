import { useEffect, useMemo, useState } from "react";
import {
  getFuelProcessedBatch,
  type FuelBvdRow,
  type FuelCanonicalTransaction,
  type FuelProcessedSummary,
} from "../../api";
import ProcessedStatementWorkspace from "./ProcessedStatementWorkspace";
import { aggregateManualEntrySummaries } from "./fuelRecentActivityDisplay";
import { applyOperationalQuantityUnitToStatementRows } from "./fuelTxnQuantityDisplay";
import { adaptManualOperationalTransactionsForProcessedStatement } from "./manualProcessedStatementAdapter";

const COLLECTION_IMPORT_ID = "manual-entry-collection";

type Props = {
  batches: FuelProcessedSummary[];
};

/**
 * All manual fuel entries in one processed view: single summary, one search/filter, one transaction grid.
 */
export default function ManualEntryCollectionWorkspace({ batches }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceRows, setSourceRows] = useState<FuelBvdRow[]>([]);
  const [canonical, setCanonical] = useState<FuelCanonicalTransaction[]>([]);
  const [cardNumber, setCardNumber] = useState("");

  const batchIds = useMemo(() => batches.map((b) => b.batch_id).join(","), [batches]);
  const collectionSummary = useMemo(() => aggregateManualEntrySummaries(batches), [batches]);

  useEffect(() => {
    if (batches.length === 0) {
      setSourceRows([]);
      setCanonical([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    void Promise.all(batches.map((b) => getFuelProcessedBatch(b.batch_id)))
      .then((details) => {
        const operational = details.flatMap((d) => d.operational_transactions ?? []);
        const gridRows = details.flatMap((d) =>
          adaptManualOperationalTransactionsForProcessedStatement(
            d.operational_transactions ?? [],
            d.source_import_ref,
          ),
        );
        setSourceRows(applyOperationalQuantityUnitToStatementRows(gridRows, operational));
        setCanonical(details.flatMap((d) => d.canonical_transactions ?? []));
        const firstCard = gridRows.find((r) => r.card_number?.trim())?.card_number?.trim();
        setCardNumber(firstCard ?? "");
      })
      .catch(() => setError("Could not load manual entry collection."))
      .finally(() => setLoading(false));
  }, [batchIds, batches.length]);

  if (loading) {
    return <p className="text-xs text-[var(--trk-text-muted)]">Loading manual entries…</p>;
  }
  if (error) {
    return <p className="text-xs text-[var(--trk-danger)]" role="alert">{error}</p>;
  }
  if (sourceRows.length === 0) {
    return <p className="text-xs text-[var(--trk-text-muted)]">No manual entries in this collection.</p>;
  }

  return (
    <article
      className="fuel-expanded-card min-w-0"
      data-testid="manual-entry-collection-workspace"
    >
      <header className="fuel-expanded-header">
        <span className="fuel-expanded-header__title">Manual Entry</span>
        <span className="fuel-expanded-header__meta">
          {batches.length} {batches.length === 1 ? "entry" : "entries"} · {collectionSummary.transaction_count}{" "}
          {collectionSummary.transaction_count === 1 ? "transaction" : "transactions"}
        </span>
      </header>

      <ProcessedStatementWorkspace
        importId={COLLECTION_IMPORT_ID}
        sourceRows={sourceRows}
        cardNumber={cardNumber}
        invoiceNumber={collectionSummary.invoice_number}
        currency={collectionSummary.currency}
        providerLabel="Manual Entry"
        manualCollectionMode
        canonicalTransactions={canonical}
        currencyFinancialSummaries={collectionSummary.currency_financial_summaries}
        providerControlTotals={collectionSummary.provider_control_totals}
      />
    </article>
  );
}
