import { useEffect, useState } from "react";
import { getFuelProcessedBatch, type FuelProcessedCurrencyFinancial } from "../../api";
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
    <div className="min-w-0 space-y-2" data-testid={`fuel-processed-shell-${batchId}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold text-[var(--trk-text)]">
          {displayLabel} {invoiceNumber}
        </h3>
        <span className="text-[10px] text-[var(--trk-text-muted)]">
          {transactionCount} transactions · {controlCount} controls · batch #{batchId}
        </span>
      </div>

      <TruckErpProcessedFuelWorkspace
        batchId={batchId}
        providerCode={providerCode}
        providerLabel={displayLabel}
        invoiceNumber={invoiceNumber}
        sourceImportRef={lineageSourceImportRef}
        currencyFinancialSummaries={currencyFinancialSummaries}
        fullInvoiceLink={
          onOpenSource ? (
            <button
              type="button"
              className="text-xs font-medium text-[var(--trk-accent)] hover:underline"
              data-testid={`fuel-open-source-${batchId}`}
              onClick={onOpenSource}
            >
              Open source
            </button>
          ) : null
        }
      />
    </div>
  );
}
