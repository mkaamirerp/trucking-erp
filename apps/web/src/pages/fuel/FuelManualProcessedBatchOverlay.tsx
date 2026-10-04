import { useEffect, useState } from "react";
import { getFuelProcessedBatch, type FuelProcessedDetail } from "../../api";
import FuelFullScreenOverlay from "./FuelFullScreenOverlay";

type Props = {
  batchId: number;
  onClose: () => void;
};

export default function FuelManualProcessedBatchOverlay({ batchId, onClose }: Props) {
  const [detail, setDetail] = useState<FuelProcessedDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getFuelProcessedBatch(batchId)
      .then(setDetail)
      .catch(() => setError("Could not load processed manual entry."))
      .finally(() => setLoading(false));
  }, [batchId]);

  const txn = detail?.operational_transactions?.[0];

  return (
    <FuelFullScreenOverlay
      open
      title="Manual fuel entry"
      subtitle={detail?.invoice_number ? `Ref ${detail.invoice_number}` : `Batch ${batchId}`}
      onClose={onClose}
      testId="fuel-manual-processed-overlay"
    >
      <div className="mx-auto max-w-3xl px-3 py-2 text-xs text-[var(--trk-text)]">
        {loading ? <p className="text-[var(--trk-text-muted)]">Loading…</p> : null}
        {error ? <p className="text-[var(--trk-danger)]" role="alert">{error}</p> : null}
        {txn ? (
          <dl className="grid gap-1 sm:grid-cols-2">
            {[
              ["Date", txn.transaction_date],
              ["Unit", txn.unit_number_snapshot],
              ["Product", txn.product],
              ["Quantity", txn.quantity != null ? `${txn.quantity} ${txn.quantity_unit ?? ""}` : "—"],
              ["Unit price", txn.unit_price],
              ["Total", txn.total_amount != null ? `${txn.total_amount} ${txn.currency ?? ""}` : "—"],
              ["Vendor", txn.merchant_site],
              ["City", txn.city],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-[10px] text-[var(--trk-text-muted)]">{label}</dt>
                <dd className="font-medium">{value ?? "—"}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </FuelFullScreenOverlay>
  );
}
