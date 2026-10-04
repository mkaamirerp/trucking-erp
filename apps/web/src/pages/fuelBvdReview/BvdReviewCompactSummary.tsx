import type { ReactNode } from "react";
import type { BvdReviewCompactSummaryModel } from "./bvdReviewCompactSummary";

function PdfIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 2h7l5 5v15a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function MetricTile({
  label,
  value,
  variant = "default",
  title,
}: {
  label: string;
  value: string;
  variant?: "default" | "reconciliation-pass" | "reconciliation-fail";
  title?: string;
}) {
  return (
    <div
      className={`bvd-compact-metric bvd-compact-metric--${variant}`}
      title={title}
      data-testid={`bvd-compact-metric-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <span className="bvd-compact-metric__label">{label}</span>
      <span className="bvd-compact-metric__value">{value}</span>
    </div>
  );
}

function ProductBreakdownBar({ segments }: { segments: BvdReviewCompactSummaryModel["productSegments"] }) {
  if (!segments.length) return null;
  return (
    <div className="bvd-compact-breakdown" data-testid="bvd-compact-product-breakdown">
      <div className="bvd-compact-breakdown__bar" role="img" aria-label="Product amount breakdown">
        {segments.map((seg) => (
          <span
            key={seg.key}
            className="bvd-compact-breakdown__segment"
            style={{
              flexGrow: seg.amount,
              backgroundColor: seg.color,
            }}
            title={`${seg.label} ${seg.amountDisplay}`}
          />
        ))}
      </div>
      <ul className="bvd-compact-breakdown__legend">
        {segments.map((seg) => (
          <li key={seg.key}>
            <span className="bvd-compact-breakdown__swatch" style={{ backgroundColor: seg.color }} />
            <span className="bvd-compact-breakdown__legend-label">{seg.label}</span>
            <span className="bvd-compact-breakdown__legend-amt">{seg.amountDisplay}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Props = {
  model: BvdReviewCompactSummaryModel;
  statusLabel: string;
  sourceHint: string;
  onOpenPdf: () => void;
  headerActions?: ReactNode;
  auditDetails?: ReactNode;
};

export default function BvdReviewCompactSummary({
  model,
  statusLabel,
  sourceHint,
  onOpenPdf,
  headerActions,
  auditDetails,
}: Props) {
  const title = model.invoiceNumber ? `BVD · Invoice ${model.invoiceNumber}` : "BVD · Import";
  const reconVariant = model.reconciliationPass ? "reconciliation-pass" : "reconciliation-fail";
  const primaryBlock = model.currencyBlocks[0];
  const multiCurrency = model.currencyBlocks.length > 1;

  const secondaryParts: string[] = [];
  if (model.purchaseCount) {
    secondaryParts.push(`${model.purchaseCount} purchase${model.purchaseCount === 1 ? "" : "s"}`);
  }
  if (model.expressCount) {
    secondaryParts.push(`${model.expressCount} Express`);
  }
  if (model.controlCount) {
    secondaryParts.push(`${model.controlCount} controls`);
  }
  const currencyLabel =
    model.currencyBlocks.length === 1 && model.currencyBlocks[0].currency !== "—"
      ? model.currencyBlocks[0].currency
      : model.currencyBlocks.length > 1
        ? model.currencyBlocks.map((b) => b.currency).join(" · ")
        : null;
  if (currencyLabel) secondaryParts.push(currencyLabel);

  const expressTitle =
    primaryBlock?.expressPrincipal && primaryBlock?.expressFees
      ? `Principal ${primaryBlock.expressPrincipal} · Fees ${primaryBlock.expressFees}`
      : undefined;

  const taxInline =
    model.taxes.length > 0
      ? model.taxes.map((t) => `${t.label} ${t.amount}`).join(" · ")
      : null;

  return (
    <section className="bvd-compact-summary" aria-label="Invoice summary" data-testid="bvd-compact-summary">
      <div className="bvd-compact-summary__header">
        <h1 className="bvd-compact-summary__title">{title}</h1>
        <div className="bvd-compact-summary__header-right">
          <span className="bvd-compact-summary__status">
            {statusLabel} · {sourceHint}
          </span>
          {headerActions}
          <button type="button" className="bvd-compact-summary__pdf" onClick={onOpenPdf}>
            <PdfIcon />
            <span>PDF</span>
          </button>
        </div>
      </div>

      <div className="bvd-compact-summary__metrics bvd-compact-summary__metrics--primary">
        <MetricTile
          label="Reconciliation"
          value={model.reconciliationLabel}
          variant={reconVariant}
        />
        {!multiCurrency && primaryBlock ? (
          <>
            <MetricTile label="Invoice" value={primaryBlock.invoiceTotal ?? "—"} />
            <MetricTile label="Qty" value={primaryBlock.qtyTotal ?? "—"} />
            <MetricTile label="Discount" value={primaryBlock.discountTotal ?? "—"} />
            <MetricTile
              label="Express"
              value={primaryBlock.expressTotal ?? "—"}
              title={expressTitle}
            />
            <MetricTile
              label="Cards"
              value={model.cardsCount > 0 ? String(model.cardsCount) : "—"}
            />
            {model.unmappedExpressCount > 0 ? (
              <span
                className="bvd-compact-summary__unmapped"
                data-testid="bvd-compact-unmapped"
                title="Express rows without category mapping"
              >
                {model.unmappedExpressCount} unmapped
              </span>
            ) : null}
          </>
        ) : null}
      </div>

      {multiCurrency ? (
        <div className="bvd-compact-summary__currency-blocks">
          {model.currencyBlocks.map((block) => (
            <div key={block.currency} className="bvd-compact-summary__currency-block">
              <div className="bvd-compact-summary__metrics">
                <span className="bvd-compact-summary__currency-tag">{block.currency}</span>
                <MetricTile label="Invoice" value={block.invoiceTotal ?? "—"} />
                <MetricTile label="Qty" value={block.qtyTotal ?? "—"} />
                <MetricTile label="Discount" value={block.discountTotal ?? "—"} />
                <MetricTile
                  label="Express"
                  value={block.expressTotal ?? "—"}
                  title={
                    block.expressPrincipal && block.expressFees
                      ? `Principal ${block.expressPrincipal} · Fees ${block.expressFees}`
                      : undefined
                  }
                />
              </div>
            </div>
          ))}
          <MetricTile
            label="Cards"
            value={model.cardsCount > 0 ? String(model.cardsCount) : "—"}
          />
        </div>
      ) : null}

      {secondaryParts.length > 0 ? (
        <p className="bvd-compact-summary__secondary" data-testid="bvd-compact-secondary-meta">
          {secondaryParts.join(" · ")}
          {taxInline ? ` · ${taxInline}` : ""}
        </p>
      ) : null}

      <div className="bvd-compact-summary__breakdown-row">
        <ProductBreakdownBar segments={model.productSegments} />
        <div className="bvd-compact-summary__audit-line">
          Audit · Controls {model.controlCount}
          {model.legendCount ? ` · Legend ${model.legendCount}` : ""}
        </div>
      </div>

      {auditDetails}
    </section>
  );
}
