import { useEffect, useState } from "react";
import { getFuelNationwideImportRows, getFuelNationwideSourceReconciliation } from "../../api";
import NationwideParsedStatementView from "../fuelNationwideReview/NationwideParsedStatementView";

type Props = {
  batchId: number;
  sourceImportRef: string | null;
  invoiceNumber: string;
  onOpenFull?: () => void;
};

export default function NationwideProcessedEvidencePanel({ sourceImportRef, onOpenFull }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Awaited<ReturnType<typeof getFuelNationwideImportRows>>>([]);
  const [reconciliation, setReconciliation] = useState<
    Awaited<ReturnType<typeof getFuelNationwideSourceReconciliation>> | null
  >(null);

  useEffect(() => {
    if (!sourceImportRef) {
      setError("Source import reference missing");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    void Promise.all([
      getFuelNationwideImportRows(sourceImportRef),
      getFuelNationwideSourceReconciliation(sourceImportRef),
    ])
      .then(([nationwideRows, nationwideReconciliation]) => {
        setRows(nationwideRows);
        setReconciliation(nationwideReconciliation);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load Nationwide statement"))
      .finally(() => setLoading(false));
  }, [sourceImportRef]);

  if (loading) {
    return <p className="text-xs text-[var(--trk-text-muted)]">Loading source evidence…</p>;
  }
  if (error) {
    return <p className="text-xs text-[var(--trk-danger)]" role="alert">{error}</p>;
  }
  if (!rows.length) {
    return <p className="text-xs text-[var(--trk-text-muted)]">No source rows for this invoice.</p>;
  }

  return (
    <NationwideParsedStatementView
      rows={rows}
      statusLabel="Processed"
      onOpenPdf={onOpenFull}
      sourceReconciliation={reconciliation}
    />
  );
}
