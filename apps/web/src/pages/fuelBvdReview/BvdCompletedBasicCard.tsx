import { Link } from "react-router-dom";
import { OPS } from "../../routes";
import { reviewStatusLabel } from "../fuelBvdReviewLabels";
import type { BvdCompletedBasicView } from "./bvdCompletedBasicProjection";
import { formatBvdSourceDate } from "./bvdUploadDuplicate";

type Props = {
  view: BvdCompletedBasicView;
  /** When true, invoice number links to full stored detail (history screen). */
  linkInvoiceToDetail?: boolean;
};

function periodLabel(start: string | null, end: string | null): string {
  const s = start ? formatBvdSourceDate(start) : "";
  const e = end ? formatBvdSourceDate(end) : "";
  if (s && e) return `${s}–${e}`;
  return s || e || "—";
}

function processedLabel(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function BvdCompletedBasicCard({ view, linkInvoiceToDetail = true }: Props) {
  const totalLine =
    view.currency && view.totalAmount
      ? `${view.totalAmount} ${view.currency}`
      : view.totalAmount || "—";

  return (
    <article
      className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
      data-read-only={view.readOnly ? "true" : "false"}
      aria-label={`${view.provider} invoice ${view.invoiceNumber}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-gray-500">{view.provider}</div>
          <h3 className="text-lg font-semibold text-gray-900">
            {linkInvoiceToDetail ? (
              <Link
                to={OPS.FUEL_BVD_DETAIL(view.importId)}
                className="text-blue-700 hover:underline"
                data-testid="bvd-invoice-detail-link"
              >
                Invoice {view.invoiceNumber}
              </Link>
            ) : (
              <>Invoice {view.invoiceNumber}</>
            )}
          </h3>
          <p className="mt-0.5 text-sm text-gray-600">
            Processed {processedLabel(view.processedAt)} · Status {reviewStatusLabel(view.reviewStatus)}
          </p>
        </div>
        {view.readOnly ? (
          <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-900">Read-only</span>
        ) : null}
      </header>

      <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-gray-500">Period</dt>
          <dd className="font-medium text-gray-900">{periodLabel(view.periodStart, view.periodEnd)}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Card</dt>
          <dd className="font-medium text-gray-900">{view.cardNumber || "—"}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Units</dt>
          <dd className="font-medium text-gray-900">{view.unitCount}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Total</dt>
          <dd className="font-medium text-gray-900">{totalLine}</dd>
        </div>
      </dl>

      {view.categories.length > 0 ? (
        <section className="mt-4" aria-label="Product categories">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Products</h4>
          <ul className="mt-1 space-y-1 text-sm">
            {view.categories.map((line) => (
              <li key={line.key} className="flex justify-between gap-4">
                <span
                  className="text-gray-800"
                  data-link-kind={line.linkKind ?? "category"}
                  data-category-key={line.key}
                >
                  {line.label}
                </span>
                <span className="font-medium tabular-nums text-gray-900">{line.amount}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {view.taxes.length > 0 ? (
        <section className="mt-4" aria-label="Taxes">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Taxes</h4>
          <ul className="mt-1 space-y-1 text-sm">
            {view.taxes.map((line) => (
              <li key={line.key} className="flex justify-between gap-4">
                <span data-link-kind={line.linkKind ?? "tax"} data-tax-key={line.key}>{line.label}</span>
                <span className="font-medium tabular-nums text-gray-900">{line.amount}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer className="mt-4 flex flex-wrap gap-2 border-t border-gray-100 pt-3">
        <Link
          to={OPS.FUEL_BVD_DETAIL(view.importId)}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
        >
          Full stored detail
        </Link>
        {!view.readOnly ? (
          <Link
            to={OPS.FUEL_BVD_REVIEW(view.importId)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-800"
          >
            Continue review
          </Link>
        ) : null}
      </footer>
    </article>
  );
}
