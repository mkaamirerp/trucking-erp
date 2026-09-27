import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listFuelBvdCompletedHistory, type FuelBvdCompletedBasic } from "../api";
import { OPS } from "../routes";
import BvdCompletedBasicCard from "./fuelBvdReview/BvdCompletedBasicCard";

export default function FuelBvdHistoryPage() {
  const [items, setItems] = useState<FuelBvdCompletedBasic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setItems(await listFuelBvdCompletedHistory());
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load Fuel history"))
      .finally(() => setLoading(false));
  }, [refresh]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Fuel history</h1>
          <p className="mt-1 text-sm text-gray-600">
            Completed provider sources — operational summary only. Click an invoice for full stored evidence.
          </p>
        </div>
        <Link to={OPS.FUEL_REVIEW} className="text-sm text-blue-700 hover:underline">
          Source review
        </Link>
      </div>

      {error ? (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
      ) : null}
      {loading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-gray-500">No completed BVD invoices yet.</p>
      ) : (
        <div className="space-y-4">
          {items.map((view) => (
            <BvdCompletedBasicCard key={view.import_id} view={mapApiToView(view)} linkInvoiceToDetail />
          ))}
        </div>
      )}
    </div>
  );
}

function mapApiToView(row: FuelBvdCompletedBasic) {
  return {
    provider: row.provider,
    importId: row.import_id,
    invoiceNumber: row.invoice_number,
    reviewStatus: row.review_status,
    readOnly: row.read_only,
    processedAt: row.processed_at,
    periodStart: row.period_start,
    periodEnd: row.period_end,
    cardNumber: row.card_number,
    unitCount: row.unit_count,
    unitNumbers: row.unit_numbers,
    totalAmount: row.total_amount,
    currency: row.currency,
    categories: row.categories.map((c) => ({ ...c, linkKind: "category" as const })),
    taxes: row.taxes.map((t) => ({ ...t, linkKind: "tax" as const })),
  };
}
