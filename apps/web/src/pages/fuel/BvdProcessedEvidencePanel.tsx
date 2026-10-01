import { useEffect, useState } from "react";
import { getFuelBvdImportRows } from "../../api";
import ProcessedStatementWorkspace from "./ProcessedStatementWorkspace";
import { parseBvdImportRowsForDashboard } from "./fuelRecentActivityRows";

type Props = {
  batchId: number;
  sourceImportRef: string | null;
  invoiceNumber: string;
  onOpenFull?: () => void;
};

export default function BvdProcessedEvidencePanel({
  sourceImportRef,
  invoiceNumber,
  onOpenFull,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<ReturnType<typeof parseBvdImportRowsForDashboard> | null>(null);

  useEffect(() => {
    if (!sourceImportRef) {
      setError("Source import reference missing");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    void getFuelBvdImportRows(sourceImportRef)
      .then((rows) => setParsed(parseBvdImportRowsForDashboard(rows)))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load BVD statement"))
      .finally(() => setLoading(false));
  }, [sourceImportRef]);

  if (loading) {
    return <p className="text-xs text-[var(--trk-text-muted)]">Loading source evidence…</p>;
  }
  if (error) {
    return <p className="text-xs text-[var(--trk-danger)]" role="alert">{error}</p>;
  }
  if (!parsed || parsed.chargeCount === 0) {
    return <p className="text-xs text-[var(--trk-text-muted)]">No accepted charges on this invoice.</p>;
  }

  return (
    <ProcessedStatementWorkspace
      importId={sourceImportRef!}
      sourceRows={parsed.sourceRows}
      invoiceNumber={invoiceNumber}
      cardNumber={parsed.cardNumber}
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
  );
}
