import { useEffect, useState } from "react";
import { getFuelProcessedBatch } from "../../api";
import TruckErpProcessedFuelWorkspace from "./TruckErpProcessedFuelWorkspace";
import { getProcessedFuelEvidenceRenderer } from "./processedFuelProviderRenderers";

export type ProcessedFuelShellProps = {
  batchId: number;
  providerCode: string;
  providerLabel: string;
  invoiceNumber: string;
  transactionCount: number;
  controlCount: number;
  sourceImportRef: string | null;
  onOpenFull?: () => void;
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
  onOpenFull,
}: ProcessedFuelShellProps) {
  const [lineageSourceImportRef, setLineageSourceImportRef] = useState<string | null>(sourceImportRef);

  const EvidencePanel = getProcessedFuelEvidenceRenderer(providerCode);

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
        fullInvoiceLink={
          onOpenFull ? (
            <button
              type="button"
              className="text-xs font-medium text-[var(--trk-accent)] hover:underline"
              onClick={onOpenFull}
            >
              Open full invoice
            </button>
          ) : null
        }
      />

      <section data-testid={`fuel-processed-evidence-${batchId}`}>
        <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
          Source evidence
        </h4>
        {EvidencePanel ? (
          <EvidencePanel
            batchId={batchId}
            sourceImportRef={lineageSourceImportRef}
            invoiceNumber={invoiceNumber}
            onOpenFull={onOpenFull}
          />
        ) : (
          <p className="text-xs text-[var(--trk-text-muted)]">No native evidence renderer for {providerCode}.</p>
        )}
      </section>
    </div>
  );
}
