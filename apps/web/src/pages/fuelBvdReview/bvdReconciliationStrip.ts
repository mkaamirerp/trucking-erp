import type { BvdParsedValidation, BvdValidationMetric } from "./bvdParsedValidation";

export type FuelBvdSourceReconciliation = {
  passed: boolean;
  transaction_total: string;
  all_unit_total: string;
  provider_grand_total: string | null;
  difference: string;
  checks: Array<{
    code: string;
    status: string;
    expected?: string | null;
    actual?: string | null;
    difference?: string | null;
    detail?: string | null;
  }>;
  currencies_seen?: string[];
};

function grandCheck(report: FuelBvdSourceReconciliation) {
  return report.checks.find((c) => c.code.includes("GRAND_TOTAL") && c.status === "FAIL") ??
    report.checks.find((c) => c.code.includes("GRAND_TOTAL"));
}

/** Map authoritative backend source-reconciliation report to review UI strip metrics. */
export function reconciliationStripFromBackend(
  report: FuelBvdSourceReconciliation | null | undefined,
): BvdParsedValidation {
  if (!report) {
    return {
      metrics: [
        { id: "invoice_amount", label: "Invoice amount", value: "—", status: "na", detail: "Loading reconciliation…" },
        { id: "units_processed", label: "Units billed", value: "—", status: "na" },
        { id: "cash_advance", label: "Cash advance", value: "—", status: "na" },
      ],
      allPass: false,
    };
  }

  const grand = grandCheck(report);
  const invoiceDetail = report.passed
    ? `Transaction total ${report.transaction_total} matches provider controls`
    : `Txn total ${report.transaction_total} vs provider ${report.provider_grand_total ?? "—"} (Δ ${report.difference})${
        grand?.code ? ` · ${grand.code}` : ""
      }`;

  const unitFail = report.checks.some(
    (c) => c.status === "FAIL" && (c.code.includes("UNIT") || c.code === "MISSING_UNIT_NONZERO_FINAL"),
  );

  const cashFail = report.checks.some((c) => c.status === "FAIL" && c.code.includes("CASH"));
  const cashCheck = report.checks.find((c) => c.code.includes("CASH"));

  const metrics: BvdValidationMetric[] = [
    {
      id: "invoice_amount",
      label: "Invoice amount",
      value: report.provider_grand_total ?? report.transaction_total,
      status: report.passed ? "pass" : "fail",
      detail: invoiceDetail,
    },
    {
      id: "units_processed",
      label: "Units billed",
      value: unitFail ? "Review units" : "OK",
      status: report.passed || !unitFail ? "pass" : "fail",
      detail: unitFail ? "Unit grouping failed under reviewed values" : undefined,
    },
    {
      id: "cash_advance",
      label: "Cash advance",
      value: cashCheck?.actual ?? "—",
      status: report.passed && !cashFail ? "pass" : cashFail ? "fail" : "na",
      detail: cashCheck?.detail ?? undefined,
    },
  ];

  return { metrics, allPass: report.passed };
}
