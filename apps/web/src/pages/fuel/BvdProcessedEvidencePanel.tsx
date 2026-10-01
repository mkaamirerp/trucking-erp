import { useEffect, useState } from "react";
import { getFuelBvdSourceReconciliation } from "../../api";

type Props = {
  batchId: number;
  sourceImportRef: string | null;
  invoiceNumber: string;
  onOpenFull?: () => void;
};

export default function BvdProcessedEvidencePanel({ sourceImportRef, onOpenFull }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [passed, setPassed] = useState<boolean | null>(null);

  useEffect(() => {
    if (!sourceImportRef) {
      setError("Source import reference missing");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    void getFuelBvdSourceReconciliation(sourceImportRef)
      .then((recon) => setPassed(recon.passed))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load BVD source evidence"))
      .finally(() => setLoading(false));
  }, [sourceImportRef]);

  if (loading) {
    return <p className="text-xs text-[var(--trk-text-muted)]">Loading source evidence…</p>;
  }
  if (error) {
    return <p className="text-xs text-[var(--trk-danger)]" role="alert">{error}</p>;
  }

  return (
    <div className="space-y-1 text-xs" data-testid="bvd-source-evidence-panel">
      <p className="text-[var(--trk-text-muted)]">
        Provider-native fields (Auth, Site, Retail, Express, controls) and original PDF are available in source
        evidence.
      </p>
      <p>
        Source reconciliation:{" "}
        <strong className={passed ? "text-[var(--trk-success)]" : "text-[var(--trk-warning)]"}>
          {passed ? "Pass" : "Review"}
        </strong>
      </p>
      {onOpenFull ? (
        <button
          type="button"
          className="font-medium text-[var(--trk-accent)] hover:underline"
          onClick={onOpenFull}
        >
          View provider-native statement
        </button>
      ) : null}
    </div>
  );
}
