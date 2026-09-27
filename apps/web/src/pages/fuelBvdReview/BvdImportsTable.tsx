import { Link } from "react-router-dom";
import type { FuelBvdImportListItem } from "../../api";
import { OPS } from "../../routes";
import { reviewStatusLabel } from "../fuelBvdReviewLabels";

type Props = {
  items: FuelBvdImportListItem[];
  title?: string;
  emptyMessage?: string;
};

export default function BvdImportsTable({ items, title, emptyMessage }: Props) {
  return (
    <section className="mt-8">
      {title ? (
        <div>
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          <p className="mt-1 text-xs text-gray-500">Latest upload per invoice — re-uploads replace older rows here.</p>
        </div>
      ) : null}
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-gray-500">{emptyMessage ?? "No BVD uploads yet."}</p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded border border-gray-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2">Invoice</th>
                <th className="px-3 py-2">File</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Uploaded</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.import_id} className="border-b last:border-0">
                  <td className="px-3 py-2 font-medium text-gray-900">{row.invoice_number}</td>
                  <td className="px-3 py-2 text-gray-600">{row.source_file_name ?? "—"}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        row.review_status === "SOURCE_REVIEWED"
                          ? "rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-900"
                          : row.review_status === "IN_REVIEW"
                            ? "rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-900"
                            : "rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900"
                      }
                    >
                      {reviewStatusLabel(row.review_status)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500">
                    {row.uploaded_at ? new Date(row.uploaded_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Link
                      to={OPS.FUEL_BVD_REVIEW(row.import_id)}
                      className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
