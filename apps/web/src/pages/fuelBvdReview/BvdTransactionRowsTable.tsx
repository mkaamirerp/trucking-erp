import { Fragment, useState, type ReactNode } from "react";
import type { FuelBvdRow } from "../../api";
import { displayCell, operationalCell } from "./bvdParsedDisplay";
import { bvdProductDisplayLabel } from "./bvdProductDisplay";
import {
  bvdTxnDiscountAmount,
  bvdTxnNonZeroTaxLines,
  bvdTxnPriceDisplay,
  formatBvdTransactionDateTime,
  formatBvdTxnLocationShort,
  formatBvdTxnSiteDetail,
} from "./bvdTransactionRowPresentation";

type Props = {
  transactions: FuelBvdRow[];
  /** From statement header — shown in expanded panel only. */
  cardNumber: string;
};

function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <span className="bvd-txn-rows__chevron" aria-hidden="true">
      {expanded ? "▾" : "▸"}
    </span>
  );
}

function DetailField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="bvd-txn-rows__detail-cell">
      <span className="bvd-txn-rows__detail-label">{label}</span>
      <span className="bvd-txn-rows__detail-value">{children}</span>
    </div>
  );
}

export default function BvdTransactionRowsTable({ transactions, cardNumber }: Props) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const toggle = (id: number) => {
    setExpandedId((cur) => (cur === id ? null : id));
  };

  return (
    <div className="bvd-statement__table-wrap bvd-txn-rows">
      <table className="bvd-statement__table bvd-statement__table--txn bvd-statement__table--purchases bvd-txn-rows__table">
        <thead>
          <tr>
            <th className="bvd-txn-rows__col-chevron" aria-hidden="true" />
            <th>Date / Time</th>
            <th>Unit</th>
            <th className="bvd-txn-rows__col-driver">Source driver</th>
            <th>Location</th>
            <th>Product</th>
            <th>Qty</th>
            <th className="bvd-txn-rows__col-amount">Final amount</th>
            <th>Currency</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((row) => {
            const expanded = expandedId === row.id;
            const taxes = bvdTxnNonZeroTaxLines(row);
            const discount = bvdTxnDiscountAmount(row);
            const prices = bvdTxnPriceDisplay(row);
            const site = formatBvdTxnSiteDetail(row);
            const finalAmt = operationalCell(row, "final_amt");
            const cur = operationalCell(row, "cur");

            return (
              <Fragment key={row.id}>
                <tr
                  className={`bvd-purchase-row bvd-txn-rows__main${expanded ? " bvd-txn-rows__main--expanded" : ""}`}
                  data-testid={`bvd-txn-row-${row.id}`}
                  data-expanded={expanded ? "true" : "false"}
                  onClick={() => toggle(row.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      toggle(row.id);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-expanded={expanded}
                >
                  <td className="bvd-txn-rows__chevron-cell">
                    <Chevron expanded={expanded} />
                  </td>
                  <td data-testid="bvd-txn-col-date">
                    {formatBvdTransactionDateTime(operationalCell(row, "transaction_date"))}
                  </td>
                  <td data-testid="bvd-txn-col-unit">{operationalCell(row, "unit_number") || "—"}</td>
                  <td data-testid="bvd-txn-col-driver">{operationalCell(row, "driver_name") || "—"}</td>
                  <td data-testid="bvd-txn-col-location">{formatBvdTxnLocationShort(row)}</td>
                  <td data-testid="bvd-txn-col-product">
                    {bvdProductDisplayLabel(operationalCell(row, "prod"))}
                  </td>
                  <td data-testid="bvd-txn-col-qty">{operationalCell(row, "qty") || "—"}</td>
                  <td data-testid="bvd-txn-col-final">{finalAmt || "—"}</td>
                  <td data-testid="bvd-txn-col-cur">{cur || "—"}</td>
                </tr>
                {expanded ? (
                  <tr key={`${row.id}-detail`} className="bvd-txn-rows__detail-row">
                    <td colSpan={9}>
                      <div
                        className="bvd-txn-rows__detail-panel"
                        data-testid={`bvd-txn-detail-${row.id}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="bvd-txn-rows__detail-grid">
                          <DetailField label="Provider">BVD</DetailField>
                          <DetailField label="Card #">{cardNumber || "—"}</DetailField>
                          <DetailField label="Auth / reference">
                            {displayCell(row, "auth_code") || "—"}
                          </DetailField>
                          <DetailField label="Site">
                            <span className="bvd-txn-rows__site-block">
                              <span>{site.primaryLine}</span>
                              {site.secondaryLine ? <span>{site.secondaryLine}</span> : null}
                              {site.siteNumberLine ? (
                                <span className="bvd-txn-rows__site-num">{site.siteNumberLine}</span>
                              ) : null}
                            </span>
                          </DetailField>
                          {prices.showRetail ? (
                            <DetailField label="Retail price">{prices.retail || "—"}</DetailField>
                          ) : null}
                          <DetailField label="Billed price">{prices.billed || "—"}</DetailField>
                          <DetailField label="Pre-tax amount">
                            {operationalCell(row, "pre_tax_amt") || "—"}
                          </DetailField>
                          {taxes.length > 0 ? (
                            <DetailField label="Taxes">
                              <span className="bvd-txn-rows__tax-list">
                                {taxes.map((t) => (
                                  <span key={t.key} data-testid={`bvd-txn-tax-${t.key}`}>
                                    {t.label} {t.amount}
                                  </span>
                                ))}
                              </span>
                            </DetailField>
                          ) : null}
                          {discount ? (
                            <DetailField label="Discount">
                              <span data-testid="bvd-txn-discount">{discount}</span>
                            </DetailField>
                          ) : null}
                          <DetailField label="Final amount">
                            {finalAmt ? `${finalAmt}${cur ? ` ${cur}` : ""}` : "—"}
                          </DetailField>
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
