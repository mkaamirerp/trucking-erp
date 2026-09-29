import { useState } from "react";
import type { FuelBvdRow } from "../../api";
import {
  BVD_FIELD_LABELS,
  BVD_HEADER_CLIENT_FIELDS,
  BVD_HEADER_DATE_FIELDS,
  BVD_HEADER_IDENTITY_STRIP_FIELDS,
  BVD_EXPRESS_COLUMNS,
  BVD_TRANSACTION_COLUMNS,
} from "../fuelBvdReviewLabels";
import BvdCorrectedFieldCell from "./BvdCorrectedFieldCell";
import { displayCell, sortBvdRows } from "./bvdParsedDisplay";
import { type BvdValidationMetric, type BvdValidationStatus } from "./bvdParsedValidation";
import {
  reconciliationStripFromBackend,
  type FuelBvdSourceReconciliation,
} from "./bvdReconciliationStrip";
import type { DraftMap } from "./bvdReviewValues";
import "./bvd-parsed-statement.css";

const TXN_COL_CLASS: Record<string, string> = {
  auth_code: "col-auth",
  driver_name: "col-driver",
  unit_number: "col-unit",
  transaction_date: "col-date",
  site_number: "col-site-num",
  site_name: "col-site-name",
  site_city: "col-city",
  prov_st: "col-prov",
  prod: "col-prod",
  qty: "col-qty",
  retail: "col-money",
  billed: "col-money",
  pre_tax_amt: "col-money",
  hst: "col-money",
  gst: "col-money",
  pst: "col-money",
  qst: "col-money",
  disc_rate: "col-money",
  disc_amt: "col-money",
  final_amt: "col-money",
  cur: "col-cur",
};

function validationStatusLabel(status: BvdValidationStatus): string {
  if (status === "pass") return "Pass";
  if (status === "fail") return "Fail";
  return "N/A";
}

function controlRowTitle(row: FuelBvdRow): string {
  const label = displayCell(row, "row_label");
  const product = displayCell(row, "product");
  if (label && product && label !== product) return `${label} (${product})`;
  return label || product || "Control row";
}

function grandTotalRowKind(row: FuelBvdRow): "statement-total" | "product-line" {
  if (displayCell(row, "row_label") === "Grand Total") return "statement-total";
  return "product-line";
}

function HeaderCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bvd-audit-details__cell">
      <span className="bvd-audit-details__label">{label}</span>
      <span className="bvd-audit-details__value">{value || "—"}</span>
    </div>
  );
}

function PdfIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 2h7l5 5v15a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" />
      <text x="7" y="17" fontSize="7" fontWeight="bold" fill="currentColor">PDF</text>
    </svg>
  );
}

function StatusCheckLine({ metric }: { metric: BvdValidationMetric }) {
  const status = validationStatusLabel(metric.status);
  const detail =
    metric.subvalue
      ? `${metric.value} (${metric.subvalue})`
      : metric.value;
  return (
    <li
      className={`bvd-status-strip__check bvd-status-strip__check--${metric.status}`}
      title={metric.detail}
    >
      <span className="bvd-status-strip__check-label">{metric.label}</span>
      <span className="bvd-status-strip__check-value">{detail}</span>
      <span className="bvd-status-strip__check-status">{status}</span>
    </li>
  );
}

type Props = {
  rows: FuelBvdRow[];
  statusLabel: string;
  onOpenPdf: () => void;
  /** processing review vs immutable full stored detail (same rows, different framing). */
  presentation?: "processing-review" | "full-stored-detail";
  /** Unsaved correction drafts (processing workspace only). */
  drafts?: DraftMap;
  /** Authoritative backend source-reconciliation (effective reviewed values). */
  sourceReconciliation?: FuelBvdSourceReconciliation | null;
  readOnly?: boolean;
  onInlineCommit?: (rowId: number, field: string, value: string) => void | Promise<void>;
};

export default function BvdParsedStatementView({
  rows,
  statusLabel,
  onOpenPdf,
  presentation = "processing-review",
  drafts = {},
  sourceReconciliation = null,
  readOnly = false,
  onInlineCommit,
}: Props) {
  const sorted = sortBvdRows(rows);
  const header = sorted.find((r) => r.row_type === "HEADER");
  const transactions = sorted.filter((r) => r.row_type === "TRANSACTION");
  const expressCharges = sorted.filter((r) => r.row_type === "EXPRESS_TRANSACTION");
  const controlRows = sorted.filter(
    (r) => r.row_type === "TRANSACTION_SUBTOTAL" || r.row_type === "PAGE1_SUMMARY",
  );
  const grandTotals = sorted.filter((r) => r.row_type === "GRAND_TOTAL");
  const legends = sorted.filter((r) => r.row_type === "LEGEND");

  const invoiceNo = header ? displayCell(header, "invoice_number") : "";
  const cardNo = header ? displayCell(header, "card_number") : "";

  const txnColumns = BVD_TRANSACTION_COLUMNS;
  const validation = reconciliationStripFromBackend(sourceReconciliation);

  const invoiceMetric = validation.metrics.find((m) => m.id === "invoice_amount");
  const unitsMetric = validation.metrics.find((m) => m.id === "units_processed");

  const [controlsOpen, setControlsOpen] = useState(false);

  const productGrandLines = grandTotals.filter((r) => grandTotalRowKind(r) === "product-line");
  const statementGrandLine = grandTotals.find((r) => grandTotalRowKind(r) === "statement-total");

  return (
    <div className="bvd-statement">
      <div className="bvd-statement__toolbar">
        <div>
          <div className="bvd-statement__title">
            {presentation === "full-stored-detail" ? "BVD full stored detail" : "BVD source review"}
          </div>
          <div className="bvd-statement__meta">
            {invoiceNo ? `Invoice ${invoiceNo} · ` : ""}
            {presentation === "full-stored-detail"
              ? `Status: ${statusLabel} · All provider fields preserved`
              : `Review status: ${statusLabel} · Parsed from upload`}
          </div>
        </div>
        <button type="button" className="bvd-statement__pdf-btn" onClick={onOpenPdf}>
          <PdfIcon />
          View original PDF
        </button>
      </div>

      <div className="bvd-statement__sheet">
        <section className="bvd-review-hero" aria-label="Reconciliation summary">
          <div
            className={`bvd-status-strip${validation.allPass ? " bvd-status-strip--ok" : " bvd-status-strip--warn"}`}
            role="status"
          >
            <div className="bvd-status-strip__headline">
              <span className="bvd-status-strip__title">Source reconciliation</span>
              <span className="bvd-status-strip__verdict">
                {validation.allPass ? "All checks passed" : "Review required before process"}
              </span>
            </div>
            <ul className="bvd-status-strip__checks">
              {validation.metrics.map((metric) => (
                <StatusCheckLine key={metric.id} metric={metric} />
              ))}
            </ul>
          </div>

          <div className="bvd-summary-cards">
            <article className="bvd-summary-card">
              <span className="bvd-summary-card__label">Invoice total</span>
              <span className="bvd-summary-card__value">{invoiceMetric?.value ?? "—"}</span>
            </article>
            <article className="bvd-summary-card">
              <span className="bvd-summary-card__label">Units billed</span>
              <span className="bvd-summary-card__value">{unitsMetric?.value ?? "—"}</span>
              {unitsMetric?.subvalue ? (
                <span className="bvd-summary-card__sub">{unitsMetric.subvalue}</span>
              ) : null}
            </article>
            <article className="bvd-summary-card">
              <span className="bvd-summary-card__label">Card #</span>
              <span className="bvd-summary-card__value">{cardNo || "—"}</span>
            </article>
          </div>

          {header ? (
            <details className="bvd-audit-details">
              <summary className="bvd-audit-details__summary">
                Invoice, client &amp; tax details (audit)
              </summary>
              <div className="bvd-audit-details__body">
                <div className="bvd-audit-details__grid">
                  <HeaderCell label="Invoice #" value={displayCell(header, "invoice_number")} />
                  {BVD_HEADER_DATE_FIELDS.map((field) => (
                    <HeaderCell
                      key={field}
                      label={BVD_FIELD_LABELS[field] ?? field}
                      value={displayCell(header, field)}
                    />
                  ))}
                  {BVD_HEADER_IDENTITY_STRIP_FIELDS.map((field) => (
                    <HeaderCell
                      key={field}
                      label={BVD_FIELD_LABELS[field] ?? field}
                      value={displayCell(header, field)}
                    />
                  ))}
                </div>
                <div className="bvd-audit-details__client">
                  {BVD_HEADER_CLIENT_FIELDS.map((field) => {
                    const val = displayCell(header, field);
                    if (!val) return null;
                    return (
                      <HeaderCell
                        key={field}
                        label={BVD_FIELD_LABELS[field] ?? field}
                        value={val}
                      />
                    );
                  })}
                </div>
              </div>
            </details>
          ) : null}
        </section>

        {transactions.length > 0 ? (
          <section className="bvd-txn-section" aria-label="Fuel card purchases">
            <h2 className="bvd-statement__section-title bvd-statement__section-title--purchases">
              Purchases ({transactions.length})
            </h2>
            <p className="bvd-section-hint">
              Only provider purchase rows — not subtotals or reconciliation controls.
            </p>
            <div className="bvd-statement__table-wrap" data-testid="bvd-purchases-full-table">
              <table className="bvd-statement__table bvd-statement__table--txn bvd-statement__table--purchases">
                <colgroup>
                  {txnColumns.map((c) => (
                    <col key={c.field} className={TXN_COL_CLASS[c.field] ?? "col-money"} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    {txnColumns.map((c) => (
                      <th key={c.field}>{c.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((row) => (
                    <tr key={row.id} className="bvd-purchase-row">
                      {txnColumns.map((c) => (
                        <td key={c.field}>
                          <BvdCorrectedFieldCell
                            row={row}
                            field={c.field}
                            drafts={presentation === "processing-review" ? drafts : {}}
                            presentation={presentation}
                            readOnly={readOnly}
                            onInlineCommit={onInlineCommit}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {expressCharges.length > 0 ? (
          <section className="bvd-txn-section" aria-label="Express charges">
            <h2 className="bvd-statement__section-title bvd-statement__section-title--purchases">
              Express charges ({expressCharges.length})
            </h2>
            <p className="bvd-section-hint">
              BVD Express Codes — provider money only; category is not assigned during extraction.
            </p>
            <div className="bvd-statement__table-wrap" data-testid="bvd-express-table">
              <table className="bvd-statement__table bvd-statement__table--txn bvd-statement__table--purchases">
                <thead>
                  <tr>
                    {BVD_EXPRESS_COLUMNS.map((c) => (
                      <th key={c.field}>{c.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {expressCharges.map((row) => (
                    <tr key={row.id} className="bvd-purchase-row">
                      {BVD_EXPRESS_COLUMNS.map((c) => (
                        <td key={c.field}>
                          {c.field === "_category" ? (
                            <span>UNMAPPED</span>
                          ) : (
                            <BvdCorrectedFieldCell
                              row={row}
                              field={c.field}
                              drafts={presentation === "processing-review" ? drafts : {}}
                              presentation={presentation}
                              readOnly={readOnly}
                              onInlineCommit={onInlineCommit}
                            />
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {controlRows.length > 0 ? (
          <section className="bvd-controls-section" aria-label="Control and reconciliation rows">
            <button
              type="button"
              className="bvd-controls-section__toggle"
              aria-expanded={controlsOpen}
              onClick={() => setControlsOpen((o) => !o)}
            >
              <span className="bvd-controls-section__toggle-label">
                Control &amp; reconciliation rows
              </span>
              <span className="bvd-controls-section__toggle-meta">
                {controlRows.length} rows · math checks, not purchases
              </span>
              <span className="bvd-controls-section__chevron" aria-hidden="true">
                {controlsOpen ? "▾" : "▸"}
              </span>
            </button>
            {controlsOpen ? (
              <div className="bvd-statement__table-wrap bvd-controls-section__table-wrap">
                <table className="bvd-statement__table bvd-statement__table--txn bvd-statement__table--controls">
                  <colgroup>
                    {txnColumns.map((c) => (
                      <col key={c.field} className={TXN_COL_CLASS[c.field] ?? "col-money"} />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      {txnColumns.map((c) => (
                        <th key={c.field}>{c.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {controlRows.map((row) => (
                      <tr key={row.id} className="bvd-control-row">
                        {txnColumns.map((c, i) => (
                          <td key={c.field}>
                            {i === 0 ? controlRowTitle(row) : displayCell(row, c.field)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        ) : null}

        {grandTotals.length > 0 ? (
          <section className="bvd-grand-section" aria-label="Grand total product breakdown">
            <h2 className="bvd-statement__section-title">Grand total breakdown</h2>
            <p className="bvd-section-hint">Product lines from page 2 — zero rows are neutral, not warnings.</p>
            <div className="bvd-grand-cards">
              {productGrandLines.map((row) => {
                const label = displayCell(row, "row_label") || displayCell(row, "product");
                const amount = displayCell(row, "final_amount") || displayCell(row, "final_amt");
                const qty = displayCell(row, "qty");
                const isZero =
                  (!amount || amount === "0.00" || amount === "0") &&
                  (!qty || qty === "0.00" || qty === "0");
                return (
                  <article
                    key={row.id}
                    className={`bvd-grand-card${isZero ? " bvd-grand-card--zero" : ""}`}
                  >
                    <span className="bvd-grand-card__label">{label}</span>
                    <span className="bvd-grand-card__amount">{amount || "—"}</span>
                    {qty ? <span className="bvd-grand-card__qty">QTY {qty}</span> : null}
                  </article>
                );
              })}
              {statementGrandLine ? (
                <article className="bvd-grand-card bvd-grand-card--statement-total">
                  <span className="bvd-grand-card__label">Grand Total</span>
                  <span className="bvd-grand-card__amount">
                    {displayCell(statementGrandLine, "final_amount") ||
                      displayCell(statementGrandLine, "final_amt")}
                  </span>
                  <span className="bvd-grand-card__qty">
                    QTY {displayCell(statementGrandLine, "qty") || "—"}
                  </span>
                </article>
              ) : null}
            </div>
          </section>
        ) : null}

        {legends.length > 0 ? (
          <details className="bvd-legend-fold">
            <summary className="bvd-legend-fold__summary">Product code legend ({legends.length})</summary>
            <div className="bvd-statement__legend">
              {legends.map((row) => (
                <div key={row.id} className="bvd-statement__legend-row">
                  <span className="bvd-statement__value">{displayCell(row, "legend_code")}</span>
                  <span className="bvd-statement__value">{displayCell(row, "legend_product_name")}</span>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </div>
  );
}
