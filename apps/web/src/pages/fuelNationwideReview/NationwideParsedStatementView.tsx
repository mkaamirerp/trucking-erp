import type { FuelNationwideRow, FuelNationwideSourceReconciliation } from "../../api";
import { NATIONWIDE_TRANSACTION_COLUMNS } from "./nationwideReviewLabels";
import { nationwideReconciliationStrip } from "./nationwideReconciliationStrip";
import { nationwideControlColumns, nationwideRowCell } from "./nationwideCellFormat";
import "../fuelBvdReview/bvd-parsed-statement.css";
import "./nationwide-parsed-statement.css";

function headerCell(row: FuelNationwideRow, field: string): string {
  return nationwideRowCell(row, field);
}

type Props = {
  rows: FuelNationwideRow[];
  statusLabel: string;
  onOpenPdf: () => void;
  sourceReconciliation: FuelNationwideSourceReconciliation | null;
};

export default function NationwideParsedStatementView({
  rows,
  statusLabel,
  onOpenPdf,
  sourceReconciliation,
}: Props) {
  const header = rows.find((r) => r.row_type === "HEADER");
  const transactions = rows.filter((r) => r.row_type === "TRANSACTION");
  const controls = rows.filter((r) => r.row_type === "CONTROL");
  const validation = nationwideReconciliationStrip(sourceReconciliation);

  return (
    <div className="bvd-statement bvd-statement--nationwide bvd-audit-details">
      <div className="nw-review-top-actions" role="status">
        <span className="nw-review-top-actions__status">{statusLabel}</span>
        <span className="nw-review-top-actions__recon">
          Reconciliation:{" "}
          <strong className={validation.allPass ? "nw-review-top-actions__pass" : "nw-review-top-actions__fail"}>
            {validation.allPass ? "Pass" : "Review"}
          </strong>
        </span>
        <button type="button" className="bvd-statement__pdf-btn" onClick={onOpenPdf}>
          View PDF
        </button>
      </div>

      <div
        className={`bvd-status-strip${validation.allPass ? " bvd-status-strip--ok" : " bvd-status-strip--warn"}`}
        aria-label="Provider reconciliation summary"
      >
        <ul className="bvd-status-strip__checks">
          {validation.metrics.map((m) => (
            <li
              key={m.label}
              className={`bvd-status-strip__check bvd-status-strip__check--${m.status}`}
              title={m.detail}
            >
              <span className="bvd-status-strip__check-label">{m.label}</span>
              <span className="bvd-status-strip__check-value">{m.value}</span>
            </li>
          ))}
        </ul>
      </div>

      {header ? (
        <section className="bvd-audit-details__header-grid">
          <div className="bvd-audit-details__cell">
            <span className="bvd-audit-details__label">Account</span>
            <span className="bvd-audit-details__value">{headerCell(header, "account_code")}</span>
          </div>
          <div className="bvd-audit-details__cell">
            <span className="bvd-audit-details__label">Invoice</span>
            <span className="bvd-audit-details__value">{headerCell(header, "invoice_number")}</span>
          </div>
          <div className="bvd-audit-details__cell">
            <span className="bvd-audit-details__label">Period</span>
            <span className="bvd-audit-details__value">
              {headerCell(header, "invoice_start_date")} – {headerCell(header, "invoice_end_date")}
            </span>
          </div>
          <div className="bvd-audit-details__cell">
            <span className="bvd-audit-details__label">Due</span>
            <span className="bvd-audit-details__value">{headerCell(header, "due_date")}</span>
          </div>
        </section>
      ) : null}

      <h2 className="bvd-statement__section-title bvd-statement__section-title--purchases">
        Purchases ({transactions.length})
      </h2>
      <div className="bvd-statement__table-wrap bvd-statement__table-wrap--nationwide">
        <table className="bvd-statement__table bvd-statement__table--txn bvd-statement__table--nationwide">
          <thead>
            <tr>
              {NATIONWIDE_TRANSACTION_COLUMNS.map((c) => (
                <th key={c.field}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {transactions.map((row) => (
              <tr key={row.id}>
                {NATIONWIDE_TRANSACTION_COLUMNS.map((c) => (
                  <td key={c.field}>{nationwideRowCell(row, c.field)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="bvd-statement__section-title">Provider controls ({controls.length})</h2>
      <ul className="nw-provider-controls">
        {controls.map((row) => {
          const cols = nationwideControlColumns(row);
          return (
            <li key={row.id} className="nw-provider-controls__row">
              <span className="nw-provider-controls__type">{cols.type}</span>
              <span className="nw-provider-controls__label">{cols.label}</span>
              <span className="nw-provider-controls__amount">{cols.amount}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
