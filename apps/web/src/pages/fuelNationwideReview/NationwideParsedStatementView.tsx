import type { FuelNationwideRow, FuelNationwideSourceReconciliation } from "../../api";
import { NATIONWIDE_TRANSACTION_COLUMNS } from "./nationwideReviewLabels";
import { nationwideReconciliationStrip } from "./nationwideReconciliationStrip";
import "../fuelBvdReview/bvd-parsed-statement.css";

function cell(row: FuelNationwideRow, field: string): string {
  const v = (row as Record<string, unknown>)[field];
  return v == null || v === "" ? "—" : String(v);
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
    <div className="bvd-statement bvd-audit-details">
      <div className="bvd-status-strip">
        <span className="bvd-status-strip__pill">{statusLabel}</span>
        <span className="bvd-status-strip__pill">
          {validation.allPass ? "Reconciliation pass" : "Reconciliation review"}
        </span>
        <button type="button" className="bvd-audit-details__pdf-btn" onClick={onOpenPdf}>
          View PDF
        </button>
      </div>
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

      {header ? (
        <section className="bvd-audit-details__header-grid">
          <div className="bvd-audit-details__cell">
            <span className="bvd-audit-details__label">Account</span>
            <span className="bvd-audit-details__value">{cell(header, "account_code")}</span>
          </div>
          <div className="bvd-audit-details__cell">
            <span className="bvd-audit-details__label">Invoice</span>
            <span className="bvd-audit-details__value">{cell(header, "invoice_number")}</span>
          </div>
          <div className="bvd-audit-details__cell">
            <span className="bvd-audit-details__label">Period</span>
            <span className="bvd-audit-details__value">
              {cell(header, "invoice_start_date")} – {cell(header, "invoice_end_date")}
            </span>
          </div>
          <div className="bvd-audit-details__cell">
            <span className="bvd-audit-details__label">Due</span>
            <span className="bvd-audit-details__value">{cell(header, "due_date")}</span>
          </div>
        </section>
      ) : null}

      <h2 className="bvd-section-title">Purchases ({transactions.length})</h2>
      <div className="bvd-table-scroll">
        <table className="bvd-txn-table">
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
                  <td key={c.field}>{cell(row, c.field)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="bvd-section-title">Provider controls ({controls.length})</h2>
      <ul className="bvd-control-list">
        {controls.map((row) => (
          <li key={row.id} className="bvd-control-list__item">
            <span className="font-medium">{row.control_type ?? "CONTROL"}</span>
            <span className="text-[var(--trk-text-muted)]">
              {row.control_line_raw ?? row.row_label ?? row.declared_amount ?? "—"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
