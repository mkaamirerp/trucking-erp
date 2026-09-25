import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fuelBvdDocumentUrl,
  getFuelBvdImportRows,
  type FuelBvdRow,
} from "../api";
import { OPS } from "../routes";

const BVD_FIELD_ORDER = [
  "invoice_number",
  "invoice_date",
  "start_date",
  "end_date",
  "due_date",
  "client_name",
  "client_address",
  "client_phone",
  "client_email",
  "card_number",
  "hst_number",
  "qst_number",
  "auth_code",
  "driver_name",
  "unit_number",
  "transaction_date",
  "site_number",
  "site_name",
  "site_city",
  "prov_st",
  "prod",
  "qty",
  "retail",
  "billed",
  "pre_tax_amt",
  "hst",
  "gst",
  "pst",
  "qst",
  "disc_rate",
  "disc_amt",
  "final_amt",
  "cur",
  "row_label",
  "product",
  "final_amount",
  "legend_code",
  "legend_product_name",
] as const;

function displayValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}

/**
 * BVD Implementation 1 — read-only extraction review.
 * LEFT: stored PDF. RIGHT: values read back from PostgreSQL (fuel_bvd).
 */
export default function FuelBvdExtractionReviewPage() {
  const { importId } = useParams();
  const [rows, setRows] = useState<FuelBvdRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!importId) return;
    const data = await getFuelBvdImportRows(importId);
    setRows(data);
  }, [importId]);

  useEffect(() => {
    if (!importId) {
      setError("Missing import id");
      setLoading(false);
      return;
    }
    setLoading(true);
    load()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load BVD rows"))
      .finally(() => setLoading(false));
  }, [importId, load]);

  const grouped = useMemo(() => {
    const order = [
      "HEADER",
      "TRANSACTION",
      "TRANSACTION_SUBTOTAL",
      "PAGE1_SUMMARY",
      "GRAND_TOTAL",
      "LEGEND",
    ];
    const map = new Map<string, FuelBvdRow[]>();
    for (const r of rows) {
      const list = map.get(r.row_type) ?? [];
      list.push(r);
      map.set(r.row_type, list);
    }
    return order.filter((t) => map.has(t)).map((t) => ({ type: t, items: map.get(t) ?? [] }));
  }, [rows]);

  if (loading) {
    return <div className="p-6 text-sm text-gray-600">Loading BVD extraction review…</div>;
  }
  if (error) {
    return (
      <div className="p-6">
        <p className="text-sm text-red-700">{error}</p>
        <Link to={OPS.FUEL_BVD_UPLOAD} className="mt-2 inline-block text-sm text-blue-700 hover:underline">
          Back to BVD upload
        </Link>
      </div>
    );
  }

  const docUrl = importId ? fuelBvdDocumentUrl(importId) : "";

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">BVD extraction review</h1>
          <p className="text-xs text-gray-500">
            Import {importId} — {rows.length} rows from database (read-only)
          </p>
        </div>
        <Link to={OPS.FUEL_BVD_UPLOAD} className="text-sm text-blue-700 hover:underline">
          Upload another PDF
        </Link>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="flex min-h-0 flex-col rounded border border-gray-200 bg-white">
          <div className="border-b px-3 py-2 text-sm font-medium text-gray-700">Original PDF</div>
          <iframe title="BVD PDF" src={docUrl} className="min-h-0 flex-1 w-full" />
        </div>
        <div className="min-h-0 overflow-auto rounded border border-gray-200 bg-white">
          <div className="sticky top-0 border-b bg-gray-50 px-3 py-2 text-sm font-medium text-gray-700">
            PostgreSQL values (fuel_bvd)
          </div>
          <div className="space-y-6 p-3">
            {grouped.map(({ type, items }) => (
              <section key={type}>
                <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{type}</h2>
                {items.map((row) => (
                  <div key={row.id} className="mb-4 rounded border border-gray-100 p-2 text-sm">
                    <div className="mb-1 text-xs text-gray-400">
                      row #{row.source_row_number} · page {row.source_page ?? "—"}
                    </div>
                    <dl className="grid grid-cols-[minmax(8rem,11rem)_1fr] gap-x-2 gap-y-1">
                      {BVD_FIELD_ORDER.map((field) => {
                        const v = row[field as keyof FuelBvdRow];
                        if (v === null || v === undefined || v === "") return null;
                        return (
                          <Fragment key={`${row.id}-${field}`}>
                            <dt className="text-gray-500">{field}</dt>
                            <dd className="font-mono text-gray-900">{displayValue(v)}</dd>
                          </Fragment>
                        );
                      })}
                    </dl>
                  </div>
                ))}
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
