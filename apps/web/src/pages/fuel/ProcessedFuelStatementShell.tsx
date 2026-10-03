import { useEffect, useState } from "react";
import {
  getFuelProcessedBatch,
  type FuelProcessedCurrencyFinancial,
  type FuelProcessedCurrencyTotal,
} from "../../api";
import TruckErpProcessedFuelWorkspace from "./TruckErpProcessedFuelWorkspace";

export type ProcessedFuelShellProps = {
  batchId: number;
  providerCode: string;
  providerLabel: string;
  invoiceNumber: string;
  transactionCount: number;
  controlCount: number;
  sourceImportRef: string | null;
  currencyFinancialSummaries?: FuelProcessedCurrencyFinancial[];
  providerControlTotals?: FuelProcessedCurrencyTotal[];
  /** Opens provider-native overlay from Fuel home (not inline on expand). */
  onOpenSource?: () => void;
};

function providerDisplayLabel(code: string, label: string): string {
  return label || code;
}

export default function ProcessedFuelStatementShell({
  batchId,
  providerCode,
  providerLabel,
  invoiceNumber,
  transactionCount,
  controlCount,
  sourceImportRef,
  currencyFinancialSummaries,
  providerControlTotals,
  onOpenSource,
}: ProcessedFuelShellProps) {
  const [lineageSourceImportRef, setLineageSourceImportRef] = useState<string | null>(sourceImportRef);

  useEffect(() => {
    setLineageSourceImportRef(sourceImportRef);
  }, [sourceImportRef, batchId]);

  useEffect(() => {
    void getFuelProcessedBatch(batchId)
      .then((detail) => {
        if (detail.source_import_ref) {
          setLineageSourceImportRef(detail.source_import_ref);
        }
      })
      .catch(() => undefined);
  }, [batchId]);

  const displayLabel = providerDisplayLabel(providerCode, providerLabel);

  return (
    <article
      className="fuel-expanded-card min-w-0"
      data-testid={`fuel-processed-shell-${batchId}`}
    >
      <header className="fuel-expanded-header">
        <span className="fuel-expanded-header__title">{displayLabel} {invoiceNumber}</span>
        <span className="fuel-expanded-header__meta">
          batch #{batchId} · {transactionCount} transactions · {controlCount} controls
        </span>
        {onOpenSource ? (
          <button
            type="button"
            className="fuel-expanded-header__link"
            data-testid={`fuel-open-source-${batchId}`}
            onClick={onOpenSource}
          >
            <span className="fuel-expanded-header__doc-icon" aria-hidden="true" />
            Open source
          </button>
        ) : null}
      </header>

      <TruckErpProcessedFuelWorkspace
        batchId={batchId}
        providerCode={providerCode}
        providerLabel={displayLabel}
        invoiceNumber={invoiceNumber}
        sourceImportRef={lineageSourceImportRef}
        currencyFinancialSummaries={currencyFinancialSummaries}
        providerControlTotals={providerControlTotals}
      />
    </article>
  );
}
