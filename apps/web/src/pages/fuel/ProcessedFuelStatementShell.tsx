import { useEffect, useState } from "react";
import { getFuelProcessedBatch, type FuelCanonicalTransaction } from "../../api";
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

function formatCanonicalMoney(value: string | null | undefined, currency: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const cur = currency?.trim();
  return cur ? `${value} ${cur}` : value;
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
  const [canonical, setCanonical] = useState<FuelCanonicalTransaction[]>([]);
  const [canonicalError, setCanonicalError] = useState<string | null>(null);
  const [canonicalLoading, setCanonicalLoading] = useState(true);
  const [lineageSourceImportRef, setLineageSourceImportRef] = useState<string | null>(sourceImportRef);

  const EvidencePanel = getProcessedFuelEvidenceRenderer(providerCode);

  useEffect(() => {
    setLineageSourceImportRef(sourceImportRef);
  }, [sourceImportRef, batchId]);

  useEffect(() => {
    setCanonicalLoading(true);
    setCanonicalError(null);
    void getFuelProcessedBatch(batchId)
      .then((detail) => {
        setCanonical(detail.canonical_transactions);
        if (detail.source_import_ref) {
          setLineageSourceImportRef(detail.source_import_ref);
        }
      })
      .catch((e: unknown) =>
        setCanonicalError(e instanceof Error ? e.message : "Could not load canonical transactions"),
      )
      .finally(() => setCanonicalLoading(false));
  }, [batchId]);

  return (
    <div className="min-w-0 space-y-2" data-testid={`fuel-processed-shell-${batchId}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold text-[var(--trk-text)]">
          {providerDisplayLabel(providerCode, providerLabel)} {invoiceNumber}
        </h3>
        <span className="text-[10px] text-[var(--trk-text-muted)]">
          {transactionCount} transactions · {controlCount} controls · batch #{batchId}
        </span>
      </div>

      <section data-testid={`fuel-processed-canonical-${batchId}`}>
        <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
          Canonical transactions
        </h4>
        {canonicalLoading ? (
          <p className="text-xs text-[var(--trk-text-muted)]">Loading canonical transactions…</p>
        ) : canonicalError ? (
          <p className="text-xs text-[var(--trk-danger)]" role="alert">{canonicalError}</p>
        ) : canonical.length === 0 ? (
          <p className="text-xs text-[var(--trk-text-muted)]">No canonical transactions.</p>
        ) : (
          <table className="w-full text-left text-[10px]">
            <thead className="text-[var(--trk-text-muted)]">
              <tr>
                <th className="py-0.5 pr-2">Product</th>
                <th className="py-0.5 pr-2">Total</th>
                <th className="py-0.5">Currency</th>
              </tr>
            </thead>
            <tbody>
              {canonical.map((txn) => (
                <tr key={txn.id} className="border-t border-[var(--trk-border)]">
                  <td className="py-0.5 pr-2">{txn.product_code_raw || "—"}</td>
                  <td className="py-0.5 pr-2 tabular-nums">
                    {formatCanonicalMoney(txn.total_amount, txn.currency_raw)}
                  </td>
                  <td className="py-0.5">{txn.currency_raw || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

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
